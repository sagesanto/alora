import os
from os.path import dirname, join, abspath
from datetime import datetime, timedelta
import pytz

from astropy.table import QTable
import astropy.units as u
from astropy.units import Quantity
from astroquery.jplhorizons import Horizons

from alora.astroutils.timeseries_cache import TimeSeriesCache
from alora.astroutils.observing_utils import dt_to_jd, jd_to_dt
from alora.config.utils import configure_logger, Config
from alora.config import logging_dir

SENTRY_DIR = dirname(abspath(__file__))
s_config = Config(join(SENTRY_DIR,"config.toml"))
logger = configure_logger("Sentry",join(logging_dir,'sentry.log'))

class SentryEphemCache(TimeSeriesCache):
    def __init__(self,logger):
        data_schema = {'desig': 'TEXT', 'start': 'REAL', 'end': 'REAL', 'generated': 'REAL', 'location': 'TEXT'}
        cache_dir = join(SENTRY_DIR,"ephem_cache")
        cache_db_path = join(cache_dir,"cache.db")
        data_lifetime_minutes = s_config["ephem_cache_lifetime_minutes"]
        super().__init__("SentryEphemCache",cache_db_path,cache_dir,data_lifetime_minutes,data_schema,logger)
    
    def remove_store_entry(self,location):
        try:
            os.remove(location)
        except FileNotFoundError:
            self.logger.error(f"Couldn't find file {location} to delete!")

    def read_data_from_store(self, location) -> (object, bool):
        if not os.path.exists(location):
            self.logger.error(f"Couldn't find file {location} to load from cache!")
            return None, False
        return QTable.read(location,format='ascii'), True
    
    def save_data_to_store(self,desig,data:QTable):
        data.sort('datetime_jd')
        min_time = jd_to_dt(min(data['datetime_jd'])).timestamp()
        max_time = jd_to_dt(max(data['datetime_jd'])).timestamp()
        location = join(self.cache_dir,f"{desig}_{min_time}_{max_time}.ecsv")
        data.write(location,format='ascii.ecsv',overwrite=True)
    
    def record_data_in_db(self, desig, data:QTable):
        generated = datetime.now(pytz.utc).timestamp()
        min_time = jd_to_dt(min(data['datetime_jd'])).timestamp()
        max_time = jd_to_dt(max(data['datetime_jd'])).timestamp()
        location = join(self.cache_dir,f"{desig}_{min_time}_{max_time}.ecsv")
        self.db.execute("INSERT INTO data (desig,start,end,generated,location) VALUES (?,?,?,?,?)",(desig,min_time,max_time,generated,location))
        self.conn.commit()
    
    def take_partial_timestep(self, desig, time: datetime) -> datetime:
        return time + timedelta(minutes=s_config["ephem_timestep_minutes"])
    
    def fetch_horizons_ephem(self,desig, start, end, quantities='1,2,3,7,9,42'):
        try:
            # self.logger.info(f"Fetching Sentry ephemerides for {desig} at {start}")
            eph = Horizons(id=desig, location=s_config["horizons_location"], epochs={"start":f"JD{dt_to_jd(start)}", "stop":f"JD{dt_to_jd(end)}", "step":f"{s_config['ephem_timestep_minutes']}m"}, id_type="smallbody").ephemerides(quantities=quantities)
        except Exception as e:
            self.logger.error(f"Failed to get Sentry ephemerides for {desig}: {e}")
            return desig, None
        return desig, eph

    async def _fetch_data(self, desigs, target_time:datetime, *args, **kwargs):
        data = {}
        self.logger.info(f"Fetching Sentry ephemerides for {desigs} at {target_time}")
        end = target_time + timedelta(hours=s_config["ephem_lookahead_hours"])
        for d in desigs:
            _, eph = self.fetch_horizons_ephem(d,target_time,end)
            if eph is None:
                data[d] = None
                continue
            eph["hour_angle"] = Quantity(eph["hour_angle"]) * 15*u.deg/u.hour          
            data[d] = eph["datetime_jd","RA","DEC","RA_app","DEC_app","RA_rate","DEC_rate","V","hour_angle"]
        
        return data
    
    

