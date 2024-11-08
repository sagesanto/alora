# Sage Santomenna 2024
#
# This class will be used to make and query a sunrise/sunset table for a given location
import os
from astral import sun, LocationInfo
from datetime import datetime, timedelta
from pytz import timezone
from astropy.time import Time
import pytz
# this import might need to be fixed:
from genUtils import stringToTime, timeToString, get_sunrise_sunset, localize
import random
from datetime import datetime, timedelta
import time
utc = pytz.UTC

SUN_TABLE_DIR = "files/sunrise_sunset_tables/"

class SunTable:
    def __init__(self, location: LocationInfo, start: datetime, end: datetime, filepath = None, time_step = timedelta(hours=6)):
        # a lookup table for sunrise/sunset times. the table is stored in a file, and the file is named based on the location, start, and end times.
        self.location = location
        self.start = localize(start)
        self.end = localize(end)
        self.time_step = time_step
        if filepath is None:
            filepath = self.make_table()
        self.filepath = filepath
        self._load()

    @classmethod
    def stringify(cls,location,start: datetime,end: datetime):
        return f"{SunTable.make_locationline(location)}_{int(start.timestamp())}_{int(end.timestamp())}"
    
    @classmethod
    def destringify(cls,filepath):
        body = filepath.split("/")[-1].split(".")[0]
        # body = filepath.split(os.sep)[-1].split(".")[0]
        lat, lon = body.split("_")[1:3]
        start, end = body.split("_")[3:5]
        start = datetime.fromtimestamp(int(start),tz=timezone("UTC"))
        end = datetime.fromtimestamp(int(end),tz=timezone("UTC"))
        return LocationInfo("","","UTC",float(lat),float(lon)), start, end

    @classmethod
    def from_file(cls,filepath):
        location, start, end = SunTable.destringify(filepath)
        with open(filepath,"r") as f:
            timestep = timedelta(hours=float(f.readline()))
        return cls(location,start,end,filepath,timestep)
    
    @staticmethod
    def make_dateline(start:datetime,end:datetime):
        return f"{timeToString(start)} - {timeToString(end)}"
    
    @staticmethod
    def make_locationline(location:LocationInfo):
        return f"sun_{int(location.latitude)}_{int(location.longitude)}"

    @staticmethod
    def parse_dateline(dateline):
        start,end = dateline.split(" - ")
        return stringToTime(start),stringToTime(end)
    
    @staticmethod
    def parse_locationline(location_line):
        lat, lon = location_line.split("_")[1,2]
        return LocationInfo("","","UTC",float(lat),float(lon))   
    
    def make_table(self):
        table_name = SunTable.stringify(self.location,self.start,self.end)
        date = self.start
        with open(os.path.join(SUN_TABLE_DIR,table_name),"w") as f:
            f.write(f"{self.time_step.total_seconds()/3600}\n")
            while date < self.end:
                sunrise, sunset = get_sunrise_sunset(self.location,date)
                f.write(f"{timeToString(date)},{timeToString(sunrise)},{timeToString(sunset)}\n")
                date += self.time_step
        return os.path.join(SUN_TABLE_DIR,table_name)
    
    def _load(self):
        # read the table into memory and store it in a dictionary
        self.table = {}
        with open(self.filepath,"r") as f:
            f.readline()
            line = f.readline()
            while line != "":
                date_str, sunrise_str, sunset_str = line.rstrip().split(",")
                d = localize(stringToTime(date_str))
                sunrise = localize(stringToTime(sunrise_str))
                sunset = localize(stringToTime(sunset_str))
                self.table[d] = (sunrise,sunset)
                line = f.readline()

    def query(self, date:datetime):
        date = localize(date)
        if not self.start < date < self.end:
            raise ValueError(f"Date {date} is outside the range of this table ({self.start} to {self.end})")
        # find the closest date in the keys of the table
        closest_date = None
        closest_sunrise = None
        closest_sunset = None
        dist = timedelta(days=1000)
        for d, (sunrise, sunset) in self.table.items():
            if abs(d-self.start) < dist:
                closest_date = d
                closest_sunrise = sunrise
                closest_sunset = sunset
                dist = abs(date-self.start)
        if closest_date is None:
            raise ValueError(f"Could not find a sunrise/sunset for {date} in table {self.filepath}, which covers {self.start} to {self.end}")
        return closest_sunrise, closest_sunset, closest_date


class SunLookup:
    def __init__(self, location: LocationInfo, around:datetime = datetime.utcnow(), time_step = timedelta(hours=6), duration = timedelta(days=60), tolerance = timedelta(hours=6)):
        self.setup()
        self.location = location
        self.duration = duration # duration to use if we need to create a table
        self.around = around
        self.time_step = time_step # time step to use if we need to create a table
        self.tolerance = tolerance # tolerance for difference between the queried time to the closest time found in the table
        self.sunrise_sunset_table, self.table_location, self.table_start, self.table_end = None, None, None, None
        self._get_table()

    def setup(self):
        if not os.path.exists(SUN_TABLE_DIR):
            os.makedirs(SUN_TABLE_DIR)
        self.tables = [f for f in os.listdir(SUN_TABLE_DIR) if f.startswith("sun_")]
        self.tablenames = [f.split(".")[0] for f in self.tables]    
    
    def _make_table(self, to=None):
        if to is None:
            to = self.around+self.duration
        self.sunrise_sunset_table = SunTable(self.location,self.around-self.time_step*2,to,time_step=self.time_step)
        self.table_location, self.table_start, self.table_end = self.sunrise_sunset_table.location, self.sunrise_sunset_table.start, self.sunrise_sunset_table.end

    def _set_details(self):
        self.table_location, self.table_start, self.table_end = self.sunrise_sunset_table.location, self.sunrise_sunset_table.start, self.sunrise_sunset_table.end

    def _get_table(self):
        location_str = SunTable.make_locationline(self.location)
        # now, do substring matching to find all tables with this location
        matching_tables = [t for t in self.tablenames if location_str in t]
        # now, find the longest-time-range table that contains the around time
        longest = timedelta(minutes=0)
        table = None
        for table_name in matching_tables:
            location, start, end = SunTable.destringify(table_name)
            if self.around.tzinfo is None:
                self.around = self.around.replace(tzinfo=timezone("UTC"))
            if start < self.around and self.around < end:
                if end-self.around > longest:
                    longest = end-start
                    table = table_name
        if table is None:
            self._make_table()
        else:
            self.sunrise_sunset_table = SunTable.from_file(os.path.join(SUN_TABLE_DIR,table))
            self._set_details()
    
    def get(self, date:datetime):
        # find the sunrise and sunset for the given date
        # if the date is outside the range of the table, we make a new table
        date = localize(date)
        if not (self.table_start < date and date < self.table_end):
            # first, warn the user that we're making a new table
            print(f"Warning: making new sunrise/sunset table for {self.location.latitude} {self.location.longitude} from {date-self.time_step*2} to {date+self.duration}")
            self._make_table(to=date+self.duration)
        sunrise, sunset, closest_date = self.sunrise_sunset_table.query(date)
        if abs(date-closest_date) > self.tolerance:
            print(f"Warning: making new table; closest date found in sunrise/sunset table {self.sunrise_sunset_table} was {closest_date}, which is outside the lookup tolerance ({self.tolerance})")
            self._make_table()
            sunrise, sunset, closest_date = self.sunrise_sunset_table.query(date)
            if abs(date-closest_date) > self.tolerance:
                raise ValueError("SunLookup tolerance error. Programmer: lower the timestep or increase the tolerance.")
        return sunrise, sunset

if __name__ == "__main__":
    # testing
    location = LocationInfo("","","UTC",34.3819,-117.6815)
    lookup = SunLookup(location,around=datetime.utcnow(),time_step=timedelta(hours=1),duration=timedelta(days=60))
    print("Lookup:",lookup.get(datetime.utcnow()))
    print("Actual:",get_sunrise_sunset(location,datetime.utcnow()))

    import numpy as np
    import matplotlib.pyplot as plt
    now = datetime.utcnow()
    end_date = now + timedelta(days=60)
    random_times = []
    for _ in range(10000):
        random_time = now + timedelta(days=random.randint(0, 60), hours=random.randint(0, 23), minutes=random.randint(0, 59))
        random_times.append(random_time)

    actuals = []
    lookups = []
    diffs = []
    lts = []
    ats = []
    for random_time in random_times:
        lookup_start = time.perf_counter()
        lt = lookup.get(random_time)
        lookup_end = time.perf_counter()
        lookups.append(lookup_end - lookup_start)

        actual_start = time.perf_counter()
        at = get_sunrise_sunset(location, random_time)
        actual_end = time.perf_counter()
        actuals.append(actual_end - actual_start)
        diffs.append(abs((lt[0]-at[0]).total_seconds()) + abs((lt[1]-at[1]).total_seconds())) 
        lts.append(lt[0].timestamp())
        lts.append(lt[1].timestamp())
        ats.append(at[0].timestamp())
        ats.append(at[1].timestamp())

    print("Lookup mean:",np.mean(lookups),"median:",np.median(lookups),"std:",np.std(lookups))
    print("Actual mean:",np.mean(actuals),"median:",np.median(actuals),"std:",np.std(actuals))
    print("Diffs mean:",np.mean(diffs),"median:",np.median(diffs),"std:",np.std(diffs))
    plt.scatter(np.arange(len(diffs)),diffs)
    # plt.scatter(lts,ats)
    plt.show()