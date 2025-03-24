import sys, os
import sqlite3
from datetime import datetime
import logging
from abc import ABC, abstractmethod
import pytz

class TimeSeriesCache(ABC):
    def __init__(self,name,cache_db_path,cache_dir,data_lifetime_minutes, data_schema, logger=None):
        os.makedirs(os.path.dirname(cache_db_path),exist_ok=True)
        self.conn = None
        self.db = None
        self.data_lifetime_s = data_lifetime_minutes * 60

        self._data_schema = data_schema
        
        assert "desig" in self._data_schema.keys(), "Data schema must have a 'desig' key that uniquely identifies the object the data is for"
        assert "location" in self._data_schema.keys(), "Data schema must have a 'location' key that indicates the path to the data"
        assert "start" in self._data_schema.keys(), "Data schema must have a 'start' key that indicates the time at the beginning of the timeseries data (NOT the time the data was generated)"
        assert "end" in self._data_schema.keys(), "Data schema must have a 'end' key that indicates the time at the end of the timeseries data"
        assert "generated" in self._data_schema.keys(), "Data schema must have a 'generated' key that indicates the time the data was generated"
        
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)
        if logger is None:
            self.logger = logging.getLogger(name)
        else:
            self.logger = logger
        self._create_db(cache_db_path)

    def _create_db(self, dbpath):
        """
        Internal. Create the database and tables for the cache
        """
        self.conn = sqlite3.connect(dbpath)

        self.db = self.conn.cursor()
        # check if the schema of the existing db is correct
        current_data_schema = {e[1]: e[2] for e in self.conn.execute("PRAGMA table_info(data)").fetchall()}
        if current_data_schema and current_data_schema != self._data_schema:
            # if it isn't, drop the table - we'll recreate it later
            self.logger.error(f"Data schema in cache database ({current_data_schema}) does not match expected schema ({self._data_schema}). Recreating.")
            self.db.executescript("DROP TABLE data;")
            self.conn.commit()
        self.db.execute(f"CREATE TABLE IF NOT EXISTS data ({','.join([f'{k} {v}' for k,v in self._data_schema.items()])})")
        self.conn.commit()

    @abstractmethod
    def remove_store_entry(self,location):
        """Remove the data entry at the given location"""
        pass

    @abstractmethod
    def read_data_from_store(self,location) -> (object,bool):
        """Read data from the cache at the given location. Returns the data and a boolean indicating if the read was successful."""
        pass

    @abstractmethod
    def save_data_to_store(self,desig,data):
        """Save data to disk. desig is the designation of the object, data is the data object."""
        pass

    @abstractmethod
    def record_data_in_db(self,desig,data):
        """Record data in the db. desig is the designation of the object, data is the data object."""
        pass

    @abstractmethod
    def take_partial_timestep(self, desig, time:datetime)->datetime:
        """Return the datetime that is a partial timestep after `time` to allow us to traverse between successive loctions for the same object if we're stuck between them"""
        # typically, just add half the typical timestep interval to the time
        #prevents us from constantly fetching data for an object when the time requested lies after the last data in a file but before data ten minutes later (the time resolution) thats in another file. happens more often than you may expect
        pass

    @abstractmethod
    async def _fetch_data(self, desigs, target_time, *args, **kwargs):
        """Fetch data for a list of designations at a given time. Returns a dictionary of {desig: data object}"""
        pass

    def cleanup_cache(self):
        """Remove old data from the cache"""
        # ephems
        # self.logger.info("Cleaning up old data from cache")
        self.db.execute("SELECT location FROM data WHERE generated < ?",(datetime.now(tz=pytz.UTC).timestamp()-self.data_lifetime_s,))
        old = self.db.fetchall()
        for o in old:
           self.remove_store_entry(o[0])
        self.db.execute("DELETE FROM data WHERE generated < ?",(datetime.now(tz=pytz.UTC).timestamp()-self.data_lifetime_s,))
        self.conn.commit()

    def find_cached_data_location(self, desig, time:datetime):
        """Find the path to a cached data for a given designation and time. Returns None if no cached data is found."""
        self.db.execute("SELECT location FROM data WHERE desig=? AND start <= ? AND end >= ? AND generated - ? <= ? ORDER BY generated DESC",(desig,time.timestamp(),time.timestamp(),datetime.now(tz=pytz.UTC).timestamp(),self.data_lifetime_s))
        location = self.db.fetchone()
        if location is not None:
            return location[0]
        return None
    
    async def get_data(self, desigs, target_time, *args, **kwargs):
        """Get data for a list of designations at a given time. Returns a dictionary of {desig: data object}"""
        need_to_fetch = []
        data = {}
        for desig in desigs:
            location = self.find_cached_data_location(desig,target_time)
            temp_time = target_time
            # this little bit prevents us from constantly fetching data for an object when the time requested lies after the last data in a file but before data ten minutes later (the time resolution) thats in another file. happens more often than you may expect
            if location is None:
                temp_time = self.take_partial_timestep(desig,target_time)
                location = self.find_cached_data_location(desig,temp_time)
            if location is not None:
                location = location
                target_time = temp_time
                d, read_successful = self.read_data_from_store(location) 
                if read_successful:
                    data[desig] = d  
                    continue 
                else:            
                    # uh oh! we found a filepath in the database but the file doesn't exist!
                    self.logger.error(f"Couldn't locate cached data for {desig} at {target_time}, despite it being in the cache database. Removing from cache database and will fetch.")
                    self.db.execute("DELETE FROM data WHERE location=?",(location,))
            else:
                # only log this message on the else clause. everything else should run if we reach this point, no else required
                self.logger.info(f"No cached data for {desig} at {target_time}. Will fetch.")
            # we don't have a cached ephem, let's get it
            need_to_fetch.append(desig)
        self.conn.commit()

        if len(need_to_fetch) > 0:
            d = await self._fetch_data(need_to_fetch,target_time,*args,**kwargs)
            if d is None:
                self.logger.error(f"Failed to get any data! {len(need_to_fetch)} data were needed at {target_time} but none were fetched.")
                return data
            # self.logger.debug("eph: "+str(eph))
            for desig in need_to_fetch:
                if d is None or desig not in d.keys() or d[desig] is None:
                    self.logger.error(f"Failed to get data for {desig} at {target_time}")
                    continue
                data[desig] = d[desig]
                self.save_data_to_store(desig,d[desig])
                self.record_data_in_db(desig,d[desig])
            self.conn.commit()
            self.cleanup_cache()
        return data