# Sage Santomenna 2024
# the observer takes incoming observation requests and observes them in order. 
# it is meant to run as a continuous service that has a monopoly on telescope and dome movement.
# i am not yet sure how much decision making about targets the observer will do, or how exactly it will interface with the database

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
from pytz import UTC


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
event_id_counter=cur.fetchone()[0]
print("Initial event id counter:",event_id_counter)
conn.close()
db_job_queue = queue.Queue()

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

lock = threading.Lock()
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
            logger.info(f"Executing database command '{command}' with args '{args}'")
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
        # conn.commit()
        # cur.execute("SELECT last_insert_rowid()")
        # res=cur.fetchone()[0]
        # conn.close()
        return event_id

def connect_to_db():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    return conn, cur

def mark_begin(record_id):
    execute_db_command("UPDATE events SET (executed_at, status) = (?,?) WHERE id = ?",(int(datetime.now().timestamp()),"executing",record_id))
    # with lock:
        # conn,cur = connect_to_db()
        # cur.execute("UPDATE events SET (executed_at, status) = (?,?) WHERE id = ?",(int(datetime.now().timestamp()),"executing",record_id))
        # conn.commit()
        # conn.close()

def mark_status(record_id,status):
    execute_db_command("UPDATE events SET status = ? WHERE id = ?",(status, record_id,))
    # with lock:
        # conn,cur = connect_to_db()
        # cur.execute("UPDATE events SET status = ? WHERE id = ?",(status, record_id,))
        # conn.commit()
        # conn.close()

def set_status_message(record_id,msg):
    execute_db_command("UPDATE events SET status_msg = ? WHERE id = ?",(msg,record_id))
    # with lock:
        # conn,cur = connect_to_db()
        # cur.execute("UPDATE events SET status_msg = ? WHERE id = ?",(msg,record_id))
        # conn.commit()
        # conn.close()

def notify(event_id,status, status_msg):
    mark_status(event_id,status)
    set_status_message(event_id,status_msg)
    with lock:
        sio.emit("event_finished",{"event_id":event_id,"status":status})

def observer(stop_event):
    logger.info("Starting observer thread")
    obs = Observatory(write_out=logger.info)
    # start by marking all previously queued events as abandoned
    execute_db_command("UPDATE events SET (status,status_msg) = (?,?) WHERE status = 'queued'",("abandoned","Abandoned by observer crash"))
    # with lock:
        # conn, cur = connect_to_db()
        # cur.execute("UPDATE events SET (status,status_msg) = (?,?) WHERE status = 'queued'",("abandoned","Abandoned by observer crash"))
        # conn.commit()
        # conn.close()
    while True:
        # stop_event is our signal to shut down
        if stop_event.is_set():
            with lock:
                conn, cur = connect_to_db()
                cur.execute("UPDATE events SET (status,status_msg) = (?,?) WHERE status = 'queued'",("abandoned","Abandoned by observer shutdown"))
                conn.commit()
                conn.close()
            return
        event = None
        try:
            event = critical_priority_queue.get(timeout=0.1)
        except queue.Empty:
            pass
        if event is None:
            try:
                event = normal_priority_queue.get(timeout=0.1)
            except queue.Empty:
                pass
        if event is None:
            try:
                event = low_priority_queue.get(timeout=0.1)
            except queue.Empty:
                pass
        if event is None:
            continue
        logger.info(f"Recieved {event.name}: id {event.id}, client {event.client}, priority {event.priority}, args {event.args}")
        mark_begin(event.id)
        try:
            event.execute(obs)
        except Exception as e:
            notify(event.id,"failed",str(e))
            logger.exception(f"Error executing event {event.name}: {e}")
        else:
            notify(event.id,"success","")

        job_state_stack.put(obs.job_state)
        dome_state_stack.put(obs.dome_state)
        logger.info(obs.job_state)
        logger.info(f"Finished executing event {event.name}")
        queues[event.priority].task_done()

# ocfg = config["ASTROMETRY"]


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

@app.route("/state",methods=["GET"])
def state():
    job_state = job_state_stack.get(timeout=0.1)
    job_state_stack.put(job_state)
    dome_state = dome_state_stack.get(timeout=0.1)
    dome_state_stack.put(dome_state)
    return jsonify({"job_state":job_state,"dome_state":dome_state,"queues":{"low":low_priority_queue.qsize(),"normal":normal_priority_queue.qsize(),"critical":critical_priority_queue.qsize()}})

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

@app.route("/",methods=["GET"])
def show():
    with lock:
        conn, cur = connect_to_db()
        cur.execute("SELECT id, event_name, client, priority, status, status_msg, created_at, executed_at FROM events ORDER BY created_at DESC")
        records = cur.fetchall()
        conn.close()
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
            </style>
        </head>
        <body>
            <h1>Observer Event Status</h1>
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
            html_content += f"""
                <tr class="{status}">
                    <td>{event_id}</td>
                    <td>{created_at}</td>
                    <td>{executed_at_str}</td>
                    <td>{event_name}</td>
                    <td>{status.capitalize()}</td>
                    <td>{client}</td>
                    <td>{priority}</td>
                    <td>{status_msg}</td?
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
    logger.info(f'Starting Astrometry server on port {ocfg["PORT"]}')
    sio.run(app, host='127.0.0.1', port=ocfg["PORT"])
    logger.info('Shutting down...')
    stop_event.set()
    observer_thread.join()
    db_thread.join()