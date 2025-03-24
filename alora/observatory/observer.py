# Sage Santomenna 2024
# the observer takes incoming observation requests and observes them in order. 
# it is meant to run as a continuous service that has a monopoly on telescope and dome movement.

import sys, os, logging
from os.path import join, dirname, abspath, basename, splitext
from abc import ABC, abstractmethod
import queue, threading
import json, requests, socket
from flask import request, jsonify, Flask
from threading import Thread, Event
import subprocess
import sqlite3
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
import numpy as np
from datetime import datetime
import numpy as np
import sqlite3
from astropy.io import fits
from astropy.table import Table
from astropy.coordinates import SkyCoord, Angle
import astropy.units as u
import ctypes
from pytz import UTC
import multiprocessing
from multiprocessing import Process, Event as mp_Event, Queue as mp_Queue, Value, Array
from multiprocessing.managers import BaseManager
import time


from alora.observatory.observatory import Observatory
# from .data_archive import Observation
from alora.config import config, configure_logger, logging_dir
import alora.observatory.observing_events as events

import warnings
warnings.filterwarnings('ignore', module="astropy.io.fits.card")
warnings.filterwarnings('ignore', module="astropy.io.fits.convenience")
warnings.filterwarnings('ignore', module="photutils.segmentation.deblend")

db_path = join(dirname(abspath(__file__)), "obs.db")
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, event_name TEXT, client TEXT, priority TEXT, status TEXT, arguments TEXT, status_msg TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, executed_at INTEGER)")
conn.commit()
cur.execute("SELECT max(id) FROM events")
event_id_counter=cur.fetchone()[0] or 0
conn.close()
db_job_queue = multiprocessing.Queue()

logger = configure_logger("Observer",join(logging_dir,"observer.log"))

low_priority_queue = queue.Queue()
normal_priority_queue = queue.Queue()
critical_priority_queue = queue.Queue()
job_state_stack = queue.LifoQueue()
job_state_stack.put("free")
dome_state_stack = queue.LifoQueue()
dome_state_stack.put("closed")

queues = {"low":low_priority_queue,"normal":normal_priority_queue,"critical":critical_priority_queue}
app = Flask(__name__)
sio = SocketIO(app)

ocfg = config["OBSERVER"]

# identify all event types in the events module
e = [v for k,v in events.__dict__.items() if isinstance(v,type) and issubclass(v,events.Event) and v != events.Event]
event_types = {cls.name:cls for cls in e}

lock = multiprocessing.Lock()
event_id_lock = threading.Lock()

def db_worker(stop_event):
    conn, cur = connect_to_db()
    logger.info("Starting database worker thread")
    while True:
        if stop_event.is_set():
            conn.close()
            return
        try:
            command, args = db_job_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        try:
            logger.debug(f"Executing database command '{command}' with args '{args}'")
            if args is not None:
                cur.execute(command,args)
            else:
                cur.execute(command)
            conn.commit()
        except Exception as e:
            logger.exception(f"Error executing database command: {e}")

def generate_event_id():
    global event_id_counter
    with event_id_lock:
        event_id_counter += 1
        return event_id_counter

def execute_db_command(command, args=None):
    db_job_queue.put((command,args))

def create_record(event_name, client, priority, arguments):
        event_id = generate_event_id()
        execute_db_command("INSERT INTO events (id, event_name, client, priority, arguments, status) VALUES (?,?,?,?,?,?)",(event_id, event_name, client, priority, arguments,"queued"))
        return event_id

def connect_to_db():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    return conn, cur

def mark_begin(record_id):
    execute_db_command("UPDATE events SET (executed_at, status) = (?,?) WHERE id = ?",(int(datetime.now().timestamp()),"executing",record_id))

def mark_status(record_id,status):
    execute_db_command("UPDATE events SET status = ? WHERE id = ?",(status, record_id,))

def set_status_message(record_id,msg):
    execute_db_command("UPDATE events SET status_msg = ? WHERE id = ?",(msg,record_id))

def notify(event_id,status, status_msg):
    mark_status(event_id,status)
    set_status_message(event_id,status_msg)
    with lock:
        sio.emit("event_finished",{"event_id":event_id,"status":status})

def set_shared_string(shared_array, value):
    value = value[:len(shared_array)]
    shared_array[:len(value)] = value
    shared_array[len(value):] = '\0' * (len(shared_array) - len(value))

def get_shared_string(shared_array):
    return ''.join(shared_array).rstrip('\0')

# process that actually holds the Observatory object and executes events. needs to be a separate process so that it can be terminated if necessary
def event_executor(stop_event, event_queue, currently_running, current_job_state, current_dome_state, event_status, event_status_msg, executor_alive):
    # need to set the state correctly here when initializing the obs (we could have been terminated and restarted)
    logger.info("Starting executor")
    obs = Observatory(write_out=logger.info)
    obs.job_state = "busy" if current_job_state.value else "free"
    obs.dome_state = "open" if current_dome_state.value else "closed"
    logger.info("Started executor.")
    
    next_event = None
    executor_alive.value = 1  # tell the main process that we're ready to go 
    while True:
        if stop_event.is_set():
            logger.info("Executor shutting down")
            return
        try:
            next_event = event_queue.get(timeout=0.1)
            currently_running.value = 1
            logger.info(f"Executor will execute event {next_event.name} ({next_event.id})")
        except queue.Empty:
            continue

        logger.info(f"Executing event {next_event.name}")
        try:
            next_event.execute(obs)
            logger.info(f'Finished executing event {next_event.name} ({next_event.id})')
            set_shared_string(event_status,"success")
            set_shared_string(event_status_msg,"")

        except Exception as e:
            logger.exception(f"Error executing event: {e}")
            set_shared_string(event_status,"failed")
            set_shared_string(event_status_msg,str(e))

        # update the states so that we can recover from a crash by reading from them
        current_job_state.value = 1 if obs.job_state == "busy" else 0
        current_dome_state.value = 1 if obs.dome_state == "open" else 0
        currently_running.value = 0
        logger.info(f"Dome is open: {current_dome_state.value}, telescope is reserved: {current_job_state.value}, event is currently running: {currently_running.value}")


def observer(stop_event):
    logger.info("Starting observer thread")

    MAX_STRING_LENGTH = 256

    event_status_arr = Array('u', MAX_STRING_LENGTH)
    event_status_msg_arr = Array('u', MAX_STRING_LENGTH)

    event_executor_stop = mp_Event()
    job_state = job_state_stack.get(timeout=0.1)
    job_state_stack.put(job_state)
    dome_state = dome_state_stack.get(timeout=0.1)
    dome_state_stack.put(dome_state)

    event_is_running = Value("i",0)
    dome_state_mp = Value("i", 1 if dome_state == "open" else 0)
    job_state_mp = Value("i", 1 if job_state == "busy" else 0)
    executor_alive = Value("i",0)

    executor_event_queue = mp_Queue()

    executor_process = Process(target=event_executor,args=(event_executor_stop,executor_event_queue,event_is_running,job_state_mp,dome_state_mp,event_status_arr,event_status_msg_arr,executor_alive),daemon=True)

    current_event = None
    # start by marking all previously queued events as abandoned
    execute_db_command("UPDATE events SET (status,status_msg) = (?,?) WHERE status = 'queued' OR status = 'executing'",("abandoned","Abandoned by observer crash"))
    executor_process.start()
    # wait for executor startup
    for i in range(100):
        if executor_alive.value:
            break
        time.sleep(0.1)
    if not executor_alive.value:
        raise ChildProcessError("Executor did not report a heartbeat after 10 seconds!")
    
    next_event = None

    event_started_time = None
    event_timeout_time = None

    while True:
        # stop_event is our signal to shut down
        if stop_event.is_set():
            logger.info("Observer shutting down")
            event_executor_stop.set()
            if event_is_running.value:
                if current_event.is_cancelable:
                    logger.info("Terminating executor")
                    executor_process.terminate()
                else:
                    logger.warning("Executor was running uncancelable task when observer stop was requested! Waiting...")
                    while event_is_running.value:
                        time.sleep(0.1)
            with lock:
                conn, cur = connect_to_db()
                cur.execute("UPDATE events SET (status,status_msg) = (?,?) WHERE status = 'queued'",("abandoned","Abandoned by observer shutdown"))
                conn.commit()
                conn.close()
            return
        
        # check for event timeout and terminate if necesssary
        if (event_timeout_time is not None) and (event_is_running.value) and (datetime.now(tz=UTC).timestamp() > event_timeout_time):
            msg = f"Event {current_event.id} timed out after {datetime.now(tz=UTC).timestamp()-event_timeout_time} seconds!"
            logger.error(msg)
            executor_process.terminate()  # horribly violent
            mark_status(current_event.id,"error")
            set_status_message(current_event.id,msg)
            notify(current_event.id,"error",msg)
            time.sleep(0.1)  # give it a second to die
            current_event = None
            job_state_stack.put("busy" if job_state_mp.value else "free")
            dome_state_stack.put("open" if dome_state_mp.value else "closed")
            event_is_running.value = 0
            set_shared_string(event_status_arr,"")
            set_shared_string(event_status_msg_arr,"")
            executor_alive.value = 0
            executor_process = Process(target=event_executor,args=(event_executor_stop,executor_event_queue,event_is_running,job_state_mp,dome_state_mp,event_status_arr,event_status_msg_arr,executor_alive),daemon=True)
            executor_process.start()
            for i in range(100):
                if executor_alive.value:
                    break
                time.sleep(0.1)
            if not executor_alive.value:
                raise ChildProcessError("Executor did not report a heartbeat after 10 seconds!")
            
        
        # report the conclusion of an event
        if (current_event is not None) and (not event_is_running.value):
            # mark the event as done
            logger.info(f"Event {current_event.id} has concluded. Reporting status...")
            event_status = get_shared_string(event_status_arr)
            event_status_msg = get_shared_string(event_status_msg_arr)
            logger.info(f"Event status: {event_status}, event status msg: {event_status_msg}")
            queues[current_event.priority].task_done()
            mark_status(current_event.id,event_status)
            if event_status_msg:
                set_status_message(current_event.id,event_status_msg)
                notify(current_event.id,event_status,event_status_msg)
            else:
                notify(current_event.id,event_status,event_status)
            job_state_stack.put("busy" if job_state_mp.value else "free")
            dome_state_stack.put("open" if dome_state_mp.value else "closed")
            set_shared_string(event_status_arr,"")
            set_shared_string(event_status_msg_arr,"")
            current_event = None
            logger.info("Status reported. Waiting for another event...")

        
        can_skip_current_event = event_is_running.value and (current_event.priority != "critical" and current_event.is_cancelable)
        if can_skip_current_event or not event_is_running.value:
            try:
                next_event = critical_priority_queue.get(timeout=0.1)
                if event_is_running.value:
                    # there's a non-critical, cancelable process running. need to terminate it
                    msg = f"This event was aborted after {round(datetime.now(UTC).timestamp()-event_started_time,3)} seconds to run critical event #{next_event.id}"
                    logger.warning(msg)
                    logger.warning("Terminating running process!")
                    executor_process.terminate()  # horribly violent
                    mark_status(current_event.id,"canceled")
                    set_status_message(current_event.id,msg)
                    notify(current_event.id,"canceled",msg)
                    time.sleep(0.1)  # give it a second to die
                    current_event = None
                    job_state_stack.put("busy" if job_state_mp.value else "free")
                    dome_state_stack.put("open" if dome_state_mp.value else "closed")
                    event_is_running.value = 0
                    set_shared_string(event_status_arr,"")
                    set_shared_string(event_status_msg_arr,"")
                    executor_alive.value = 0
                    executor_process = Process(target=event_executor,args=(event_executor_stop,executor_event_queue,event_is_running,job_state_mp,dome_state_mp,event_status_arr,event_status_msg_arr,executor_alive),daemon=True)
                    executor_process.start()
                    for i in range(100):
                        if executor_alive.value:
                            break
                        time.sleep(0.1)
                    if not executor_alive.value:
                        raise ChildProcessError("Executor did not report a heartbeat after 10 seconds!")
            except queue.Empty:
                pass

        if next_event is None and not event_is_running.value:
            try:
                next_event = normal_priority_queue.get(timeout=0.1)
            except queue.Empty:
                pass

        if next_event is None and not event_is_running.value:
            try:
                next_event = low_priority_queue.get(timeout=0.1)
            except queue.Empty:
                pass

        if next_event is None:
            continue

        logger.info(f"Recieved {next_event.name}: id {next_event.id}, client {next_event.client}, priority {next_event.priority}, args {next_event.args}")
        
        # if we reach this point, we have an event to run
        logger.info(f"Requesting execution of event {next_event.id}.")
        assert current_event == None and event_is_running.value==0

        current_event = next_event
        next_event = None
        
        assert executor_event_queue.empty(), "Executor event queue was not empty when we tried to put an event in it!"
        mark_begin(current_event.id)
        event_started_time = datetime.now(tz=UTC).timestamp()
        if current_event.timeout is not None:
            event_timeout_time = event_started_time + 2 + current_event.timeout
        else:
            event_timeout_time = None
        executor_event_queue.put(current_event)  # this is where we actually start the event
        time.sleep(0.1)

# show info for each event type
@app.route(f"/info/<event_name>",methods=["GET"])
def event_info(event_name):
    if event_name not in event_types:
        return "Event not found", 404
    return jsonify(event_types[event_name].as_dict())

# links to info pages for each event type
@app.route("/info",methods=["GET"])
def info_page():
    res = ""
    for cls in e:
        res += f"<a href='/info/{cls.name}'>{cls.name}</a><br>"
    return res

# handle incoming events
@app.route("/exec/<event_name>",methods=["POST"])
def handle_event(event_name):
    if event_name not in event_types:
        return jsonify({"status":"failed","error":"Event not found"}), 404
    data = request.get_json()
    missing = [field for field in ["client","priority","args"] if field not in data]
    if missing:
        return jsonify({"status":"failed","error":f"Missing required fields {missing}"}), 500
    try:
        event = event_types[event_name](**data)
    except Exception as e:
        logger.exception(f"Error creating event: {e}")
        return jsonify({"status":"failed","error": str(e)}), 500
    if event.priority not in queues:
        return jsonify({"status":"failed","error": "Invalid priority"}), 500
    event_id = create_record(event_name, data["client"], data["priority"], json.dumps(data["args"]))
    event.id = event_id
    queues[event.priority].put(event)
    return jsonify({"status":"ok","event_id":event_id}), 200

@app.route("/status",methods=["GET"])
def state():
    job_state = job_state_stack.get(timeout=0.1)
    job_state_stack.put(job_state)
    dome_state = dome_state_stack.get(timeout=0.1)
    dome_state_stack.put(dome_state)
    return jsonify({"job_state":job_state,"dome_state":dome_state,"queues":{"low":low_priority_queue.qsize(),"normal":normal_priority_queue.qsize(),"critical":critical_priority_queue.qsize()}})

@app.route("/show/obs_status",methods=["GET"])
def show_obs_status():
    job_state = job_state_stack.get(timeout=0.1)
    job_state_stack.put(job_state)
    dome_state = dome_state_stack.get(timeout=0.1)
    dome_state_stack.put(dome_state)
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Observatory Status</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 20px;
            }
            h1 {
                color: #333;
            }
            .status {
                font-size: 1.2em;
                margin: 10px 0;
            }
            .status span {
                font-weight: bold;
            }
        </style>
    </head>""" + f""" 
    <body>
        <h1>Observatory Status</h1>
        <div class="status">
            <p>Job State: {job_state.capitalize()}</p>
            <p>Dome State: {dome_state.capitalize()}</p>
        </div>
    </body>
    </html>
    """

@app.route("/event/<event_id>",methods=["GET"])
def event_status(event_id):
    conn,cur = connect_to_db()
    cur.execute("SELECT * FROM events WHERE id = ?",(event_id,))
    res = cur.fetchone()
    conn.close()
    if res is None:
        return jsonify("Event not found"), 404
    return jsonify(dict(res))

@app.route("/events",methods=["GET"])
def events_list():
    conn,cur = connect_to_db()
    cur.execute("SELECT * FROM events")
    res = cur.fetchall()
    conn.close()
    return jsonify([dict(r) for r in res])

@app.route("/show/event/<event_id>",methods=["GET"])
def show_event(event_id):
    conn,cur = connect_to_db()
    cur.execute("SELECT * FROM events WHERE id = ?",(event_id,))
    record = cur.fetchone()
    if record is None:
        return "Event not found", 404
    event_id, event_name, client, priority, status, arguments, status_msg, created_at, executed_at = record
    conn.close()

    if executed_at is not None:
        executed_at = datetime.fromtimestamp(executed_at, tz=UTC)
        executed_at_str = executed_at.strftime('%Y-%m-%d %H:%M:%S')
    else:
        executed_at_str = "N/A"

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Event {event_id}</title>""" + """
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 20px;
            }
            h1 {
                color: #333;
            }
        </style>
    </head>
    <body>""" + f"""
        <h1>Event {event_id}</h1>
        <p><b>Event Name:</b> <a href=/info/{event_name}> {event_name} </a></p>
        <p><b>Client:</b> {client}</p>
        <p><b>Priority:</b> {priority.capitalize()}</p>
        <p><b>Status:</b> {status.capitalize()}</p>
        <p><b>Status Message:</b> {status_msg}</p>
        <p><b>Arguments:</b> {arguments}</p>
        <p><b>Created At:</b> {created_at}</p>
        <p><b>Executed At:</b> {executed_at_str}</p>
    </body>
    </html>
    """

@app.route("/",methods=["GET"])
def show():
    with lock:
        conn, cur = connect_to_db()
        cur.execute("SELECT id, event_name, client, priority, status, status_msg, created_at, executed_at FROM events ORDER BY created_at DESC")
        records = cur.fetchall()
        conn.close()
        job_state = job_state_stack.get(timeout=0.1)
        job_state_stack.put(job_state)
        dome_state = dome_state_stack.get(timeout=0.1)
        dome_state_stack.put(dome_state)
        html_content = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Observer Event Status</title>
            <style>
                table {
                    width: 100%;
                    border-collapse: collapse;
                }
                th, td {
                    border: 1px solid #ddd;
                    padding: 8px;
                    text-align: left;
                }
                th {
                    background-color: #f2f2f2;
                }
                .executing {
                    background-color: lightblue;
                }
                .failed {
                    background-color: lightcoral;
                }
                .success {
                    background-color: lightgreen;
                }
                .queued {
                    background-color: gray;
                    color: white;
                }
                .abandoned {
                    background-color: lightgray;
                }
                .canceled {
                    background-color: yellow;
                }
            </style>
        </head>""" + f"""
        <body>
            <h1>Observer Event Status</h1>
            <p><b>Reservation State:</b> {job_state.capitalize()}  |  <b>Dome State:</b> {dome_state.capitalize()}  |  <b>Low Priority Enqueued:</b> {low_priority_queue.qsize()}  |  <b>Normal Priority Enqueued:</b> {normal_priority_queue.qsize()}  |  <b>Critical Priority Enqueued:</b> {critical_priority_queue.qsize()}</p>
            <table>
                <tr>
                    <th>Event ID</th>
                    <th>Date Requested (UTC)</th>
                    <th>Date Executed (UTC)</th>
                    <th>Event Name</th>
                    <th>Status</th>
                    <th>Client</th>
                    <th>Priority</th>
                    <th>Status Message</th>
                </tr>
        """

        for record in records:
            #id, event_name, client, priority, status, status_msg, created_at, executed_at
            event_id, event_name, client, priority, status, status_msg, created_at, executed_at = record
            if executed_at is not None:
                executed_at = datetime.fromtimestamp(executed_at, tz=UTC)
                executed_at_str = executed_at.strftime('%Y-%m-%d %H:%M:%S')
            else:
                executed_at_str = "N/A"
            start_tag = "<td><b>" if priority == "critical" else "<td>"
            end_tag = "</b></td>" if priority == "critical" else "</td>"

            html_content += f"""
                <tr class="{status}">
                    {start_tag}<a href='/show/event/{event_id}'>{event_id}</a><br>{end_tag}
                    {start_tag}{created_at}{end_tag}
                    {start_tag}{executed_at_str}{end_tag}
                    {start_tag}{event_name}{end_tag}
                    {start_tag}{status.capitalize()}{end_tag}
                    {start_tag}{client}{end_tag}
                    {start_tag}{priority.capitalize()}{end_tag}
                    {start_tag}{status_msg}{end_tag}
                </tr>
            """

        html_content += """
            </table>
        </body>
        </html>
        """
        return html_content


if __name__ == '__main__':
    stop_event = Event()        
    observer_thread = Thread(target=observer, args=(stop_event,))
    observer_thread.start()
    db_thread = Thread(target=db_worker, args=(stop_event,))
    db_thread.start()
    logger.info(f'Starting observing server on port {ocfg["PORT"]}')
    sio.run(app, host='127.0.0.1', port=ocfg["PORT"])   
    logger.info('Shutting down...')
    stop_event.set()
    observer_thread.join()
    db_thread.join()
    logger.info("Shutdown complete. Bye!")