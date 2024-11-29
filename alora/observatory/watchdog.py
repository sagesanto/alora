import os
from os.path import dirname, join
from alora.observatory.observatory import Observatory
import socket
import time
from alora.observatory.config import configure_logger, config
from alora.observatory.telemetry.sensors.tempest_weather_sensor import TempestWeatherSensor
from alora.observatory.choir import Vocalist

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

def is_weather_safe():
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
                        logger.warning(f"Failed weather check! {k} {v[0]} {v[1]}")
                        notify("warning",f"Failed weather check! {k} {v[0]} {v[1]}")
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
    DROP_LIMIT = 3

    i = 0
    dropped = 0
    close_if_unsafe = True
    weather_safe = True
    write_out(f"Watching for internet dropouts ({address_to_monitor}:{port})...")
    write_out(f"Watching weather...")
    while True:
        # check skyx connection
        if not o.telescope.connected:
            notify("critical","Dome-close watchdog lost connection to skyx - will not be able to close in an emergency!!")

        # check internet
        r = ping(address_to_monitor,port)
        if not r:
            dropped += 1
            if dropped <= DROP_LIMIT:
                write_out(f"Dropped a connection! Consecutive drops: {dropped}")
        else:
            if dropped >= DROP_LIMIT:
                write_out("Connection regained.")
            dropped = 0
        if dropped == DROP_LIMIT and close_if_unsafe:
            write_out("CLOSING DUE TO DROPPED CONNECTION")
            notify("warning","Shutting down observatory due to dropped internet connection!")
            close()
            write_out("Waiting for internet connection...")
        
        # check weather
        if i % 30 == 0:
            i = 1
            weather_safe = is_weather_safe()
            if weather_safe and close_if_unsafe:
                write_out("Weather is safe, resuming monitoring")
            if not weather_safe and close_if_unsafe:
                write_out("CLOSING DUE TO WEATHER")
                notify("warning","Shutting down observatory because of bad weather conditions!")
                close()  
                write_out("Waiting for safe weather...")
        
        close_if_unsafe = weather_safe and dropped < DROP_LIMIT  # to prevent repeatedly closing the dome

        i += 1
        time.sleep(1)

if __name__ == "__main__":
    run_watchdog("google.com",80)