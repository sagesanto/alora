import os
from os.path import dirname, join
from alora.observatory.observatory import Observatory
import socket
import time
from alora.observatory.config import configure_logger, config
from alora.observatory.telemetry.sensors.tempest_weather_sensor import TempestWeatherSensor

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
                else:
                    logger.warning(f"Was asked to check for '{k}' in weather for {crit_name}, but couldn't find it.")
    except Exception as e:
        raise e
        logger.error(f"Weather safety check failed! {e}")
    return safe

def close():
    global o
    while True:
        try:
            o.close()
            return
        except Exception as e:
            logger.error(f"FUCK!! Trying to close but can't: {str(e)}")
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
        if dropped == DROP_LIMIT and close_if_unsafe:  # == instead of >= prevents us from repeatedly closing the dome
            write_out("CLOSING DUE TO DROPPED CONNECTION")
            close()
            write_out("Waiting for internet connection...")
        
        # check weather
        if i % 60 == 0:
            i = 1
            weather_safe = is_weather_safe()
            if not weather_safe and close_if_unsafe:
                write_out("CLOSING DUE TO WEATHER")
                close()  
                write_out("Waiting for safe weather...")
        
        close_if_unsafe = weather_safe and dropped < DROP_LIMIT  # to prevent repeatedly closing the dome

        i += 1
        time.sleep(1)

if __name__ == "__main__":
    run_watchdog("google.com",80)