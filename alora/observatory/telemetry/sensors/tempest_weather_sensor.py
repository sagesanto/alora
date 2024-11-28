import requests
import time, os
from threading import Timer, Lock

from alora.observatory.telemetry.sensor import SensorService
from alora.observatory.config import config, get_credential

class TempestWeatherSensor:
    def __init__(self, logger):
        self.logger = logger
        self.session = None
        self.token = None
        self.last_measurement_timestamp = None
        self.base_url = config["WEATHER_URL"]
    
    def setup(self):
        self.token = get_credential("weather","token")
        self.session = requests.Session()
        self.station_ID = self.get_station_ID()

    def get_station_ID(self):
        url = f"{self.base_url}/stations?token={self.token}"
        r = self.session.get(url, timeout=5)
        return r.json()["stations"][0]["station_id"]
    
    def get_observation(self, fields=None):
        url = f"{self.base_url}/observations/station/{self.station_ID}?token={self.token}&units_temp=c&units_wind=mps&units_pressure=mb&units_precip=mm&units_distance=km"
        if fields is not None:
            url += "&ob_fields=" + ",".join(fields)
        r = self.session.get(url, timeout=5)
        j = r.json()    
        if j["status"]["status_code"] != 0:
            raise ChildProcessError(f"Weather station failed to report observation, error message given was '{j['status']['status_message']}'")
        return j["obs"][0]
    
    def get_forecast(self):
        url = f"{self.base_url}/better_forecast?station_id={self.station_ID}&token={self.token}&units_temp=c&units_wind=mps&units_pressure=mb&units_precip=mm&units_distance=km"
        r = self.session.get(url, timeout=5)
        j = r.json()    
        if j["status"]["status_code"] != 0:
            raise ChildProcessError(f"Weather station failed to report forecast, error message given was '{j['status']['status_message']}'")
        return j["forecast"]


class TempestWeatherService(SensorService):
    def __init__(self, sensor_name: str, table_name: str, blueprint: dict, polling_interval=1, local_db_name="default"):
        super().__init__(sensor_name, table_name, blueprint, polling_interval, local_db_name)
        self.logger.info(f"Initialized weather sensor {self.sensor_name}")
        self.sensor = TempestWeatherSensor(self.logger)
        self.last_measurement_timestamp = None

    def start_taking_measurements(self):
        self.sensor.setup()
        self.stop = False
        self.logger.info(f"Starting to take measurements with interval {self.interval}")
        self.take_measurement()

    def take_measurement(self):
        if self.stop:
            self.logger.info("Can't take measurement: stopped!")
            return
        try:
            obs = self.sensor.get_observation(fields=list(self.blueprint.keys()))
        except Exception as e:
            self.logger.error(f"Can't get observation! Exception: {str(e)}")
        else:
            try:
                # need to do this bc the telem table already has a 'timestamp' col: 
                obs["obs_timestamp"] = obs["timestamp"]
                del(obs["timestamp"]) 

                if obs["obs_timestamp"] == self.last_measurement_timestamp:
                    self.logger.warning(f"Measurement was stale, will check again in half an interval ({self.interval/2}s)")
                    t = Timer(self.interval/2, self.take_measurement)
                    t.daemon = True
                    t.start()
                    return
                
                # remove extra keys we were given back
                for k in list(obs.keys()):
                    if k not in self.blueprint.keys():
                        del(obs[k])

                obs["SensorName"] = self.sensor_name
                self.send_measurement(obs)
                self.last_measurement_timestamp = obs["obs_timestamp"]

            except Exception as e:
                self.logger.error(f"Can't log observation! Exception: {str(e)}")
            
        t = Timer(self.interval, self.take_measurement)
        t.daemon = True
        t.start()

if __name__ == "__main__":
    blueprint = {
    'air_density': ["FLOAT","kg/m3"],
    'air_temperature': ["FLOAT", "C"],
    'barometric_pressure': ["FLOAT", "mb"],
    'brightness': ["INT","lux"],
    'delta_t': ["FLOAT", "C"],
    'dew_point': ["FLOAT", "C"],
    'heat_index': ["FLOAT", "C"],
    'lightning_strike_count': ["INT", "unitless"],
    'lightning_strike_last_distance': ["INT","km"],
    'lightning_strike_last_epoch': ["INT","s"],
    'precip': ["FLOAT","mm"],
    'precip_accum_last_1hr': ["FLOAT","mm"],
    'pressure_trend': ['TEXT','unitless'],
    'relative_humidity': ["INT","percent"],
    'sea_level_pressure': ["FLOAT","mb"],
    'solar_radiation': ["INT","w/m2"],
    'station_pressure': ["FLOAT","mb"],
    'obs_timestamp': ["INT","s"],
    'uv': ["FLOAT","unitless"],
    'wet_bulb_globe_temperature': ["FLOAT", "C"],
    'wet_bulb_temperature': ["FLOAT", "C"],
    'wind_avg': ["FLOAT", "m/s"],
    'wind_chill': ["FLOAT", "C"],
    'wind_direction': ["INT","degrees"],
    'wind_gust': ["FLOAT", "m/s"],
    'wind_lull': ["FLOAT", "m/s"]}

    s = TempestWeatherService("TempestWeather", "Weather",blueprint,polling_interval=60)
    s.write_service()