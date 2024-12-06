import os
from os.path import dirname, join
from alora.observatory.observatory import Observatory
import socket
import time
from alora.observatory.config import configure_logger, config
from alora.observatory.telemetry.sensors.tempest_weather_sensor import TempestWeatherSensor
from alora.observatory.choir import Vocalist
import flask
from queue import Queue, LifoQueue, Empty
from threading import Thread

reactivate_queue = Queue()
safe_state_queue = LifoQueue()

def api():
    app = flask.Flask(__name__)

    @app.route("/resume", methods=["GET"])
    def resume_monitoring():
        reactivate_queue.put(True,timeout=0.5)
        return "OK"

    @app.route("/status", methods=["GET"])
    def get_status():
        state = safe_state_queue.get(timeout=0.5)
        safe_state_queue.put(state,timeout=0.5)
        return {"safe_to_open": state}

    app.run(host="127.0.0.1",port=config["WATCHDOG_PORT"])

# from https://stackoverflow.com/a/67217558
def ping(server: str, port: int, timeout=3):
    """ping server"""
    try:
        socket.setdefaulttimeout(timeout)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((server, port))
    except OSError as error:
        return False
    else:
        s.close()
        return True

logpath = join(dirname(__file__),'watchdog.log')
logger = configure_logger("watchdog",outfile_path=logpath)

def write_out(*args,**kwargs):
    logger.info(" ".join([str(a) for a in args]))

weather_sensor = TempestWeatherSensor(logger)
weather_sensor.setup()
o = Observatory(write_out=write_out)
vocalist = Vocalist("Dome Watchdog")

def notify(severity,msg):
    try:
        vocalist.notify(severity, "Observatory Shutdown", msg)
    except Exception as e:
        logger.error(f"Couldn't send notification: {e}")

def is_weather_safe(do_notif:bool):
    funcs = {">": lambda a,b: a>b, "<": lambda a,b: a<b, "==": lambda a,b: a==b}
    forecast = weather_sensor.get_forecast()
    current = weather_sensor.get_observation()
    forecast = forecast["hourly"][0]  # forecast for the next hour
    criteria = config["WEATHER_CONDITIONS_CLOSE"]
    safe = True
    try:
        for crit_name, measured in zip(("FORECAST", "NOW"), (forecast,current)):
            crit = criteria[crit_name]
            for k,v in crit.items():
                if k in measured.keys():
                    safe = safe and not funcs[v[0]](measured[k],v[1])   # compare measured value (forecast[k]) with criteria val (v[1]) using comparison func (v[0])
                    if not safe:
                        if do_notif:
                            logger.warning(f"Failed weather check! {crit_name} {k} {v[0]} {v[1]}")
                            notify("warning",f"Failed weather check! {crit_name} {k} {v[0]} {v[1]}")
                else:
                    logger.warning(f"Was asked to check for '{k}' in weather for {crit_name}, but couldn't find it.")
    except Exception as e:
        logger.error(f"CRITICAL: Weather safety check failed due to unexpected error: {e}")
        notify("critical",f"Weather safety check failed due to error: {e}")
        return False
        # raise e
    return safe

def close():
    global o
    i = 0
    while True:
        try:
            o.close()
            if i > 0:
                notify("info","Dome closed.")  # if dome previously was failing to close, let everyone know that that issue has been resolved
            return
        except Exception as e:
            logger.error(f"FUCK!! Trying to close but can't: {str(e)}")
            if i % 30 == 0:  # avoid too much spam, once a minute is enough?
                notify("critical", f"FUCK!! Trying to do emergency observatory shutdown but can't: {str(e)}")
            o = Observatory(write_out=write_out)
            time.sleep(2)


def run_watchdog(address_to_monitor,port):
    global o
    DROP_LIMIT = 3

    state = "active"  # once we close, we go into standby until the condition is resolved (to prevent spam)
    i = 0
    dropped = 0  # number of times we dropped a conn
    weather_safe = True  # is it safe to operate?
    lost_skyx = False  # have we lost the skyx connection?
    check_weather_now = False
    check_skyx_now = False

    safe_state_queue.put(True)  # will be updated when weather and internet get checked
    first_check = True
    api_thread = Thread(target=api)
    api_thread.daemon=True
    api_thread.start()

    write_out(f"Watching for internet dropouts ({address_to_monitor}:{port})...")
    write_out(f"Watching weather...")
    while True:
        try:
            if reactivate_queue.get(timeout=0.5):
                state = "active"
                check_weather_now = True
                check_skyx_now = True
                logger.info("Activating due to web request")
        except Empty:
            continue

        ### SKYX CHECK
        if i % 5 == 0 or check_skyx_now:
            check_skyx_now = False
            if not o.telescope.connected:
                if not lost_skyx:
                    notify("critical","Dome-close watchdog lost connection to skyx - will not be able to close in an emergency!!")
                    logger.error("Dome-close watchdog lost connection to skyx - will not be able to close in an emergency!!")
                lost_skyx = True
                safe_state_queue.put(False,timeout=0.2)
                o = Observatory(write_out=write_out)
            elif lost_skyx:
                notify("info", "Connection to SkyX regained.")
                logger.info("Connection to SkyX regained.")
                safe_state_queue.put(dropped<DROP_LIMIT and weather_safe,timeout=0.2)
                lost_skyx = False


        ### INTERNET CHECK
        r = ping(address_to_monitor,port)
        if not r:  # dropped a connection
            dropped += 1
            if dropped <= DROP_LIMIT:
                write_out(f"Dropped a connection! Consecutive drops: {dropped}")
        else: # got a ping
            if dropped >= DROP_LIMIT:  # did we just regain connection?
                dropped = 0  # yes it seems redundant but it's not, we need to reset the counter if we've just regained conn so that the safe_state_queue gets updated correctly
                write_out("Connection regained.")
                safe_state_queue.put(dropped<DROP_LIMIT and weather_safe and not lost_skyx,timeout=0.2)
            dropped = 0  
        if dropped >= DROP_LIMIT and state=="active":  # close if we've dropped too many connections
            write_out("CLOSING DUE TO DROPPED CONNECTION")
            notify("warning","Shutting down observatory due to dropped internet connection!")
            safe_state_queue.put(False,timeout=0.2)
            close()
            write_out("Waiting for internet connection...")

        ### WEATHER CHECK
        if i % 30 == 0 or check_weather_now:
            i = 1
            check_weather_now = False
            was_unsafe = not weather_safe
            weather_safe = is_weather_safe(do_notif = state=="active")
            if weather_safe and was_unsafe:
                write_out("Weather is safe again")
                safe_state_queue.put(dropped<DROP_LIMIT and weather_safe and not lost_skyx,timeout=0.2)
            if not weather_safe and state=="active":
                write_out("CLOSING DUE TO WEATHER")
                notify("warning","Shutting down observatory because of bad weather conditions!")
                safe_state_queue.put(False,timeout=0.2)
                close()  
                write_out("Waiting for safe weather...")
        

        # if we're in standby, check if we can go back to active
        state = "active" if weather_safe and dropped < DROP_LIMIT else "standby" # to prevent repeatedly closing the dome

        if first_check:
            first_check = False
            safe_state_queue.put(dropped<DROP_LIMIT and weather_safe and not lost_skyx,timeout=0.2)

        i += 1
        time.sleep(1)

if __name__ == "__main__":
    run_watchdog("google.com",80)