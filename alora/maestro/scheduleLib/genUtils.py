# Sage Santomenna 2023
# Many general utilities and the definition of the TypeConfiguration class

import sys, os
from os.path import join, dirname, abspath
import logging
import re, json
from datetime import timedelta, datetime, timezone
from typing import Union
import astral
# print(abspath(logging.__file__))
import astroplan
import astropy.time
import pytz
from astral import LocationInfo
from astral import sun
from astropy import units as u
from astropy.coordinates import Angle, Longitude
import logging.config
from astropy.time import Time
from abc import ABCMeta, abstractmethod
import pandas as pd
from pytz import UTC as dtUTC
from importlib import import_module

from alora.astroutils.obs_constraints import ObsConstraint

tmo = ObsConstraint()

_logger = logging.getLogger(__name__)

MAESTRO_DIR = abspath(join(dirname(__file__), os.path.pardir))

def get_candidate_database_path():
    settings_path = join(MAESTRO_DIR, "MaestroCore","settings.txt")
    with open(settings_path, "r") as settingsFile:
        settings = json.load(settingsFile)
    return settings["candidateDbPath"][0]

def generate_candidate_class(config_name,config_constructors,config_serializers,config_schema,base_candidate_class):
    class ModuleCandidate(base_candidate_class):
    # class ModuleCandidate(BaseCandidate):
        def __init__(self, CandidateName: str, **kwargs):

            self.CandidateName = CandidateName
            # TODO: don't hardcode the module name here (but circular import?)
            self.CandidateType = config_name
            self.config_schema = config_schema
            self.config_constructors = config_constructors
            self.config_serializers = config_serializers
            super().__init__(self.CandidateName, self.CandidateType, **kwargs)

    return ModuleCandidate

def configure_logger(name):
    # first, check if the logger has already been configured
    if logging.getLogger(name).hasHandlers():
        return logging.getLogger(name)

    try:
        with open(join(MAESTRO_DIR,"logging.json"), 'r') as log_cfg:
            logging.config.dictConfig(json.load(log_cfg))
        logger = logging.getLogger(name)
        # set the out logfile to a new path
    except Exception as e:
        print(f"Can't load logging config ({e}). Using default config.")
        logger = logging.getLogger(name)
        file_handler = logging.FileHandler(join(join(MAESTRO_DIR,"main.log")),mode="a+")
        logger.addHandler(file_handler)
    return logger

class LoggerFilter(logging.Filter):
    def filter(self, record):
        return record.levelno in [logging.INFO, logging.DEBUG, logging.WARNING]


class ScheduleError(Exception):
    """!Exception raised for user-facing errors in scheduling
    @param message: explanation of the error
    """

    def __init__(self, message="No candidates are visible tonight"):
        self.message = message
        super().__init__(self.message)


class TypeConfiguration(metaclass=ABCMeta):
    """!
    The TypeConfiguration class is a class subclassed by each Config module. Must be constructed and returned by the
    getConfig() function in the TypeConfiguration's schedule_[config_name].py file.
    """

    @abstractmethod
    def __init__(self, scorer: astroplan.Scorer, maxMinutesWithoutFocus=60, numObs=1,
                 minMinutesBetweenObs=None):
        """!

        @param scorer:
        @param maxMinutesWithoutFocus: max time, in minutes, that this object can be scheduled after the most recent focus loop
        @param numObs: how many different times should this target be observed
        @param minMinutesBetweenObs: minimum time, in minutes, between the start times of multiple observations of the same object
        """
        self.scorer = scorer
        self.maxMinutesWithoutFocus = maxMinutesWithoutFocus  #
        self.numObs = numObs
        self.minMinutesBetweenObs = minMinutesBetweenObs  #

    @abstractmethod
    def generateSchedulerLine(self, row, targetName, candidateDict, spath):
        """!
        Given a row from the schedule dataframe, the name of the target, and the candidate dictionary, the config must return a line or list of lines to put in the schedule
        @rtype: str|list
        """
        pass

    @abstractmethod
    def selectCandidates(self, startTimeUTC: datetime, endTimeUTC: datetime, dbPath):
        """!
        Provided a start time, end time, and the path to the database, retrieve and return a collection of Candidates that the scheduler should attempt to schedule
        """
        pass

    @abstractmethod
    def generateTransitionDict(self):
        """!
        Return a dictionary that specifies how targets of this type should transition to and from other observations. See MPC config for an example
        """
        pass

    @abstractmethod
    def generateTypeConstraints(self):
        """!
        Return astroplan Constraints that should be applied to all targets of this type
        """
        pass

    @abstractmethod
    def scoreRepeatObs(self, c, scoreLine, numPrev, currentTime):
        """!
        Given a candidate c, its score row, the number of times it's been previously observed, and the current time, return a score row for use when scheduling another observation of the same target
        @return: a series or array of the same length as scoreLine
        """
        pass


def timeToString(dt, logger=_logger, scheduler=False, shh=False):
    """!
    Format a datetime as a string
    @type dt: datetime
    """
    try:
        # if we get a string, check that it's valid by casting it to dt. If it isn't, we'll return None
        if isinstance(dt, str):  
            dt = stringToTime(dt)
        return dt.strftime("%Y-%m-%d %H:%M:%S") if not scheduler else dt.strftime("%Y-%m-%dT%H:%M:%S.000")
    except Exception as e:
        if logger and not shh:
            logger.error(f"Unable to coerce time from {dt}: {e}")
        return None

def write_out(*args):
    sys.stdout.write(" ".join([str(x) for x in args]) + "\n")
    sys.stdout.flush()

def jd_to_dt(hjd):
    time = Time(hjd, format='jd', scale='tdb')
    return time.to_datetime().replace(tzinfo=pytz.UTC)

def dt_to_jd(dt):
    return Time(dt).jd

class AutoFocus:
    def __init__(self, desiredStartTime):
        """!
        Create an AutoFocus line for the scheduler
        @param desiredStartTime:
        """
        self.startTime = ensureDatetime(desiredStartTime)
        self.endTime = self.startTime + timedelta(minutes=5)

    def genLine(self):
        return "\n"+genericScheduleLine(0,0,"CLEAR",self.startTime,"Focus", "Refocusing", 0, 0, move=False, guiding=False, offset=False,ROI_height=0,ROI_width=0,ROI_start_x=0,ROI_start_y=0)
        # return "\n" + timeToString(self.startTime, scheduler=True) + "|1|Focus|0|0|0|0|0|CLEAR|0|0|0|0|0|0|0|0|'Refocusing'\n"

    @classmethod
    def fromLine(cls, line):
        time = line.split('|')[0]
        time = stringToTime(time)
        return cls(time)

SCHEDULE_SCHEMA_PATH = join(MAESTRO_DIR, dirname(__file__),"schedule_schema.json")

with open(SCHEDULE_SCHEMA_PATH,"r") as f:
    schedule_schema = json.loads(f.read())

def scheduleHeader():
    """!
    Return the (static) header for the scheduler line
    """
    return "|".join(list(schedule_schema.keys()))
    # return "DateTime|Occupied|Target|Move|RA|Dec|ExposureTime|#Exposure|Filter|Bin2Fits|Guiding|Offset|CandidateID|ROIHeight|ROIWidth|ROIStartX|ROIStartY|BinningSize|Description"

def fill_schedule_line(arg_dict:dict):
    """Make a schedule line from a dictionary of field:value pairs, filling in default values for missing ones (where possible)

    :param arg_dict: dictionary that specifies `field`:`value`, where `field` exactly matches a key in the schedule schema. If a `field`'s `value` is `None`, it will be replaced with the default `value` for that `field`, if one exists. If no default `value` exists for a `field` and its `value` is not provided, an error will be raised 
    :type arg_dict: _type_
    :raises ScheduleError: raised if `field`s are provided that do not match the schedule schema
    :raises ScheduleError: raised if `arg_dict`'s keys is missing fields that have no default value specified in the schedule schema
    :rtype: str
    """

    # make blank line
    line_dict = {k:schedule_schema[k].get("default") for k in schedule_schema.keys()}
    
    bad_keys = []
    # copy over provided info
    for k,v in arg_dict.items():
        if k not in line_dict.keys():
            bad_keys.append(k)
            continue
        if arg_dict[k] is not None:
            line_dict[k]=v
    if bad_keys:
        raise ScheduleError(f"Requested schedule line contained illegal keys {bad_keys}. To allow new keys in the schedule, modify {SCHEDULE_SCHEMA_PATH}")
    
    missing_keys = []
    # fill in with unfilled slots with defaults
    for k,v in line_dict.items():
        if v is None:
            missing_keys.append(k)
    if missing_keys:
        raise ScheduleError(f"Tried to make schedule line but no value provided for field(s) {missing_keys} in args {arg_dict}. To allow field(s) to be blank, add a 'default' key to the field in {SCHEDULE_SCHEMA_PATH}.")
    
    line_vals = [str(line_dict[k]) for k in schedule_schema.keys()]  # double check that our keys are in the correct order

    return "|".join(line_vals)


def findCenterTime(startTime: datetime, duration: timedelta):
    """!
    Find the nearest ten minute interval to the center of the time window {start, start+duration}
    @param startTime: datetime object representing the start of the window
    @param duration: timedelta representing the length of the window
    @return: datetime representing the center of the window, rounded to the nearest ten minutes
    """
    center = startTime + (duration / 2)
    return roundToTenMinutes(center)


def angleToDMSString(angle, format="colonSep"):
    """!
    Format an astropy Angle as a DMS string
    @type angle: Angle
    @param format: "colonSep" or "hmsdms"
    @rtype: str
    """
    degrees = abs(int(angle.dms[0]))
    sign = "-" if angle < 0 else "+"  # ughhhh
    minutes = abs(int(angle.dms[1]))
    seconds = abs(angle.dms[2])
    if format == "colonSep":
        return f"{sign}{degrees:02d}:{minutes:02d}:{seconds:05.2f}"
    if format == "hmsdms":
        return f"{sign}{degrees:02d}d{minutes:02d}m{seconds:05.2f}s"


def angleToHMSString(angle, format="colonSep"):
    """!
    Format an astropy Angle as an HMS string
    @type angle: Angle
    @param format: "colonSep" or "hmsdms"
    @rtype: str
    """
    hours = abs(int(angle.hms[0]))
    sign = "-" if angle < 0 else ""  # ughhhh
    minutes = abs(int(angle.hms[1]))
    seconds = abs(angle.hms[2])

    if format == "colonSep":
        return f"{sign}{hours:02d}:{minutes:02d}:{seconds:05.2f}"
    if format == "hmsdms":
        return f"{sign}{hours:02d}h{minutes:02d}m{seconds:05.2f}s"


def genericScheduleLine(RA, Dec, filterName: str, startDt:datetime, name:str, description:str, exposureTime, exposures, move=None, bin2fits=None,
                        guiding=None, offset=None, ROI_height=None,ROI_width=None,ROI_start_x=None, ROI_start_y=None, binning_size=None, CandidateID=None):
    """!
    Generate a generic schedule line. If optional arguments are left as `None`, they will be set to the default value for that field
    @param RA: right ascension of the target, as Angle or in degrees
    @type RA: Angle|float|str
    @param filterName: name of filterwheel filter to use
    @param startDt: datetime at start of observation
    @param name: name of candidate as it should appear in the schedule
    @param description: description for schedule
    @param exposureTime: Seconds per exposure.
    @type exposureTime: float|int|str
    @param exposures: Number of exposures
    @type exposures: int|str
    @param move: should the telescope move from its previous location to this one before observing?
    @type move: bool
    @param bin2fits: should the telescope convert binary files to fits files
    @type bin2fits: bool
    @param guiding: should the telescope guide during this observation?
    @type guiding: bool
    @return: line to insert into schedule text file
    @rtype: str
    """
    for arg in [move,bin2fits,guiding,offset]:
        if isinstance(arg,bool):
            arg = "1" if arg else "0"

    line_dict = {}
    line_dict["DateTime"] = timeToString(startDt, scheduler=True)
    line_dict["Occupied"] = "1"
    line_dict["Target"] = name
    line_dict["Move"] = "1" if move else "0"
    line_dict["RA"] = str(ensureFloat(RA))
    line_dict["Dec"] = str(ensureFloat(Dec))
    line_dict["ExposureTime"] = str(exposureTime)
    line_dict["#Exposure"] = str(exposures)
    line_dict["Filter"] = filterName
    line_dict["Bin2Fits"] = "1" if bin2fits else "0"
    line_dict["Guiding"] = "1" if guiding else "0"
    line_dict["Offset"] = "1" if offset else "0"
    line_dict["CandidateID"] = str(CandidateID)
    line_dict["ROIHeight"] = ROI_height
    line_dict["ROIWidth"] = ROI_width
    line_dict["ROIStartX"] = ROI_start_x
    line_dict["ROIStartY"] = ROI_start_y
    line_dict["BinningSize"] = binning_size
    line_dict["Description"] = "\"" + description + "\""

    return fill_schedule_line(line_dict)


def inputToAngle(text, hms=True):
    """
    Function to try to convert user string into datetime. developed for use in app, may be generally useful
    @rtype: Angle
    """
    try:
        return ensureAngle(float(text))
    except:
        pass

    dh, minutes, *seconds = map(float, [t for t in re.split("[:dhms]", text) if t])
    sign = text[0] if text[0] in ("+", "-") else ""
    if hms:
        text = f"{sign}{abs(int(dh))}h{int(minutes)}m{seconds[0]}s" if seconds else f"{sign}{abs(int(dh))}h{int(minutes)}m"
    else:
        text = f"{sign}{abs(int(dh))}d{int(minutes)}m{seconds[0]}s" if seconds else f"{sign}{abs(int(dh))}d{int(minutes)}m"
    return ensureAngle(text)

def readStdin():
    """!
    Guess what this one does (hint: it reads standard input)
    """
    return sys.stdin.readline()


def ensureDatetime(time, logger=_logger):
    """!
    Convert the provided time object to a datetime according to known formats
    @param time:
    @param logger:
    @rtype: datetime
    """
    if isinstance(time, datetime):
        return time
    if isinstance(time, str):
        try:
            return stringToTime(time)
        except:
            if logger is not None:
                logger.error("Couldn't make datetime from string " + time)
            raise
    if isinstance(time, astropy.time.Time):
        return time.to_datetime()


def stringToTime(timeString, logger=_logger, scheduler=False):
    """!
    Attempt to convert a string to a datetime using common formats
    @param timeString:
    @param logger:
    @return: converted time or None
    @rtype: datetime
    """

    try:
        return datetime.strptime(timeString, "%Y-%m-%d %H:%M:%S")
    except:
        try:
            return datetime.strptime(timeString, "%Y-%m-%d %H:%M:%S.%f")
        except Exception as e:
            print(repr(e))
            if logger:
                logger.error("Unable to coerce time from " + timeString)
    return None


# def toDecimal(angle: Angle):
#     """!
#     Return the decimal degree representation of an astropy Angle, as a float
#     @return: Decimal degree representation, float
#     """
#     return round(float(angle.degree), 6)  # ew


def toSexagesimal(angle: Angle):
    """!
    Return the sexagesimal representation of an astropy angle, as a string
    @param angle:
    @return: string
    """
    return angle.to_string()


from alora.astroutils.observing_utils import ensureAngle

# def ensureAngle(angle):
#     """!
#     Return angle as an astropy Angle, converting if necessary
#     @param angle: float, int, hms Sexagesimal string, hms tuple, or astropy Angle
#     @return: angle, as an astropy Angle
#     """
#     if not isinstance(angle, Angle):
#         try:
#             if isinstance(angle, str) or isinstance(angle, tuple):
#                 angle = Angle(angle)
#             else:
#                 angle = Angle(angle, unit=u.deg)
#         except Exception as err:
#             print("Error converting", angle, "to angle")
#             raise err
#     return angle


from alora.astroutils.observing_utils import ensureFloat

# def ensureFloat(angle):
#     """!
#     Return angle as a float, converting if necessary
#     @rtype angle: float, Angle
#     @return: decimal angle, as a float
#     """
#     try:
#         if isinstance(angle, str) or isinstance(angle, tuple):
#             angle = Angle(angle)
#             return ensureFloat(angle)  # lol
#     except:
#         pass
#     if isinstance(angle, float):
#         return angle
#     if isinstance(angle, Angle):
#         return toDecimal(angle)
#     else:
#         return float(angle)


def roundToTenMinutes(dt):
    """!
    Round a datetime object to the nearest 10 minutes
    @type dt: datetime
    @return: rounded time
    @rtype: datetime
    """
    dt += timedelta(minutes=5)
    return dt - timedelta(minutes=dt.minute % 10, seconds=dt.second, microseconds=dt.microsecond)


from alora.astroutils.observing_utils import angleToTimedelta

# def angleToTimedelta(angle: Angle):  # low precision
#     """!
#     Convert an astropy Angle to an timedelta whose duration matches the hourangle of the angle
#     @rtype: timedelta
#     """
#     angleTime = angle.to(u.hourangle)
#     angleHours, angleMinutes, angleSeconds = angleTime.hms
#     return timedelta(hours=angleHours, minutes=angleMinutes, seconds=0)

def overlapping_time_windows(start1: datetime, end1: datetime, start2: datetime, end2: datetime):
    """!
    Determine the overlap between two time windows, (start1, end1) and (start2, end2). Time windows do not need to be provided in chronological order.
    @param start1: start time of first window
    @type start1: datetime
    @param end1: end time of first window
    @type end1: datetime
    @param start2: start time of second window
    @type start2: datetime
    @param end2: end time of second window
    @type end2: datetime
    @return: overlap_start, overlap_end
    @rtype: datetime, datetime
    """
    if not start1 or not start2 or not end1 or not end2:
        return None, None
    if pd.isnull(start1) or pd.isnull(start2) or pd.isnull(end1) or pd.isnull(end2):
        return None, None
    if start1 <= start2:
        early_start = start1
        early_end = end1
        late_start = start2
        late_end = end2
    else:
        early_start = start2
        early_end = end2
        late_start = start1
        late_end = end1
    # determine if there is overlap
    if early_end <= late_start:
        return None, None
    # determine the overlap
    overlap_start = late_start
    overlap_end = min(early_end, late_end)
    return overlap_start, overlap_end

static_observability_window = tmo.static_observability_window

# def staticObservabilityWindow(RA: Angle, Dec: Angle, locationInfo: astral.LocationInfo, dt: Union[datetime, str] = "now"):
#     """!
#     Generate the TMO observability window for a static target based on RA, dec, and location. Optionally, provide a datetime to find the observability window for a future time.
#     @param RA: right ascension
#     @type RA: Angle, float, int, hms Sexagesimal string, or hms tuple
#     @param Dec: declination
#     @type Dec: Angle, float, int, dms Sexagesimal string, or dms tuple
#     @param locationInfo: astral LocationInfo object for the observatory site
#     @type locationInfo: astral.LocationInfo
#     @param dt: datetime to find the observability window for. If "now" (default), use the current time.
#     @type dt: datetime|str
#     @return: [startTime, endTime]
#     @rtype: list(datetime)
#     """
#     if dt == "now":
#         t = findTransitTime(RA, locationInfo)
#     else:
#         t = findFutureTransitTime(RA, locationInfo, dt)
#     limits = get_hour_angle_limits(Dec)
#     if limits is None:
#         return None, None
#     timeWindow = (angleToTimedelta(a) for a in limits)
#     return [t + a for a in timeWindow]
#     # HA = ST - RA -> ST = HA + RA

observation_viable = tmo.observation_viable

# def observationViable(RA, Dec, dt, locationInfo):
#     """!
#     Is the object with RA, Dec observable at time dt?
#     """
#     # siderealDay = timedelta(hours=23, minutes=56, seconds=4.091)  # lol
#     window = static_observability_window(RA, Dec, dt)
#     if window is None:
#         return False
#     # i think (and hope) that this isn't necessary, so im commenting it out:
#     # if window[0] and window[1]:
#     #     # if the whole window is behind us, shift it forward one sidereal day. cheap trick
#     #     if window[1] < datetime.utcnow():
#     #         window[0] += siderealDay
#     #         window[1] += siderealDay
#     try:
#         return pytz.UTC.localize(window[0]) < dt < pytz.UTC.localize(window[1])
#     except ValueError:
#         # the window already has a timezone
#         return window[0] < dt < window[1]


from alora.astroutils.observing_utils import current_dt_utc

# def current_dt_utc():
    # return datetime.utcnow().replace(tzinfo=dtUTC)



from alora.astroutils.observing_utils import get_current_sidereal_time

# def get_current_sidereal_time(locationInfo):
#     now = current_dt_utc().replace(second=0, microsecond=0)
#     return Time(now).sidereal_time('mean', longitude=locationInfo.longitude)

from alora.astroutils.observing_utils import find_transit_time

# def find_transit_time(rightAscension: Angle, location):
#     """!Calculate the transit time of an object at the given location.

#     @param rightAscension: The right ascension of the object as an astropy Angle
#     @type rightAscension: Angle, float, int, hms Sexagesimal string, or hms tuple
#     @param location: The observatory location.
#     @type location: astral.LocationInfo
#     @return: The transit time of the object as a datetime object.
#     @rtype: datetime.datetime
#     """
#     rightAscension = ensureAngle(rightAscension)
#     currentTime = datetime.utcnow().replace(second=0, microsecond=0)
#     lst = Time(currentTime).sidereal_time('mean', longitude=location.longitude)
#     ha = rightAscension - lst
#     transitTime = currentTime + angleToTimedelta(ha)
#     return transitTime

# def findFutureTransitTime(rightAscension: Angle, location, dt: datetime):
#     """!Calculate the transit time nearest the dt of an object at the given location.

#     @param rightAscension: The right ascension of the object as an astropy Angle
#     @type rightAscension: Angle, float, int, hms Sexagesimal string, or hms tuple
#     @param location: The observatory location.
#     @type location: astral.LocationInfo
#     @param dt: The datetime near which to find the next transit time.
#     @type dt: datetime.datetime
#     @return: The transit time of the object as a datetime object.
#     @rtype: datetime.datetime
#     """
#     rightAscension = ensureAngle(rightAscension)
#     assert(isinstance(dt, datetime))
#     dt = dt.replace(second=0, microsecond=0)
#     lst = Time(dt).sidereal_time('mean', longitude=location.longitude)
#     ha = rightAscension - lst
#     transitTime = dt + angleToTimedelta(ha)
#     return transitTime


def query_to_dict(queryResults):
    """!
    Convert SQLite query results to a list of dictionaries.
    @param queryResults: List of SQLite query row objects.
    @return: List of dictionaries representing query results.
    """
    dictionary = [dict(row) for row in queryResults if row]
    return [{k: v for k, v in a.items() if v is not None} for a in dictionary if a]


def filter(record):
    info = sys.exc_info()
    if info[1]:
        logging.exception('Exception!', exc_info=info)
        print("---Exception!---", info)
        raise
    return True

TMO_loc = LocationInfo(name="TMO", region="CA, USA", timezone="UTC", latitude=34.36,
                    longitude=-117.63)

def localize(dt):
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    return dt

def import_maestro_modules():
    root = "schedulerConfigs"
    root_directory = join(MAESTRO_DIR, root)
    module_names = []
    for dir in [f"{root}."+d for d in os.listdir(root_directory) if os.path.isdir(os.path.join(root_directory, d))]:
        module_names.append(dir)
    modules = {}
    for m in module_names:
        try:
            modules[m.replace("_"," ").replace(f"{root}.","")] = import_module(m, "schedulerConfigs")
        except Exception as e:
            write_out(f"Can't import config module {m}: {e}. Fix and try again.")
            raise e
    return modules
            


get_sunrise_sunset = tmo.get_sunrise_sunset

# def get_sunrise_sunset(loc=TMO_loc,dt=datetime.utcnow()):
#     """!
#     get sunrise and sunset for TMO
#     @return: sunriseUTC, sunsetUTC
#     @rtype: datetime.datetime
#     """
#     dt = localize(dt)
#     s = sun.sun(loc.observer, date=dt, tzinfo=timezone.utc)
#     sunriseUTC = s["sunrise"]
#     sunsetUTC = sun.time_at_elevation(loc.observer, -10, direction=sun.SunDirection.SETTING,date=dt)

#     # TODO: make this less questionable - it probably doesn't do exactly what i want it to when run at certain times of the day:
#     if sunriseUTC < dt:  # if the sunrise we found is earlier than the current time, add one day to it (approximation ofc)
#         sunriseUTC = sunriseUTC + timedelta(days=1)

#     if sunsetUTC > sunriseUTC:
#         sunsetUTC = sunsetUTC - timedelta(days=1)

#     return sunriseUTC, sunsetUTC


# # TODO: make observatory super easy to change - nothing specialized to TMO
# def get_sunrise_sunset():
#     """!
#     get sunrise and sunset for TMO
#     @return: sunriseUTC, sunsetUTC
#     @rtype: datetime.datetime
#     """
#     TMO = LocationInfo(name="TMO", region="CA, USA", timezone="UTC", latitude=34.36,
#                        longitude=-117.63)

#     s = sun.sun(TMO.observer, date=datetime.now(timezone.utc), tzinfo=timezone.utc)
#     sunriseUTC = s["sunrise"]
#     sunsetUTC = sun.time_at_elevation(TMO.observer, -10, direction=sun.SunDirection.SETTING)

#     nowDt = datetime.utcnow()
#     nowDt = pytz.UTC.localize(nowDt)

#     # TODO: make this less questionable - it probably doesn't do exactly what i want it to when run at certain times of the day:
#     if sunriseUTC < nowDt:  # if the sunrise we found is earlier than the current time, add one day to it (approximation ofc)
#         sunriseUTC = sunriseUTC + timedelta(days=1)

#     if sunsetUTC > sunriseUTC:
#         sunsetUTC = sunsetUTC - timedelta(days=1)

#     return sunriseUTC, sunsetUTC


def f(x):
    return round(float(x), 2)

def tS(time):
    """!
    Format start time for observing log
    @param time: start time
    @type time: datetime
    @return:
    """
    return stringToTime(time).strftime("%H:%M") + " - "


def tE(time):
    """!
    Format end time for observing log
    @param time: ending time
    @type time: datetime
    @return:
    """
    return stringToTime(time).strftime("%H:%M")


def xor(a, b):
    return (a and not b) or (not a and b)


def prettyFormat(candidateDf):
    """Format a candidate df to be more user friendly.

    @param candidateDf: The DataFrame containing the candidate information.
    @type candidateDf: pandas.DataFrame
    @returns: pandas.DataFrame
    """

    columns = ["CandidateName", "Processed", "Submitted", "Observability", "TransitTime", "RA",
               "Dec", "dRA", "dDec", "Magnitude", "ApproachColor"]

    formattedDf = candidateDf.copy()

    formattedDf["RA"] = formattedDf["RA"].apply(
        lambda x: (Angle(x, unit=u.degree)).to_string(unit=u.hour, sep=":"))
    formattedDf["Dec"] = formattedDf["Dec"].apply(lambda x: Angle(x, unit=u.degree).to_string(unit=u.degree, sep=":"))
    if "RMSE_RA" in formattedDf.columns:
        formattedDf["RMSE"] = tuple(zip(formattedDf["RMSE_RA"].apply(f), formattedDf["RMSE_Dec"].apply(f)))
        columns = ["CandidateName", "Processed", "Submitted", "Observability", "TransitTime", "RA",
               "Dec", "dRA", "dDec", "Magnitude",
               "RMSE", "ApproachColor"]  # inelegant but whatever
    formattedDf["Observability"] = formattedDf["StartObservability"].apply(tS) + formattedDf["EndObservability"].apply(
        tE)

    formattedDf = formattedDf[columns]

    return formattedDf

get_hour_angle_limits = tmo.get_hour_angle_limits

# def get_hour_angle_limits(dec):
#     """
#     Get the hour angle limits of the target's observability window based on its dec.
#     @param dec: float, int, or astropy Angle
#     @return: A tuple of Angle objects representing the upper and lower hour angle limits
#     """
#     dec = ensureFloat(dec)

#     horizonBox = {  # {tuple(decWindow):tuple(minAlt,maxAlt)}
#         (-35, -34): (-35, 42.6104),
#         (-34, -32): (-35, 45.9539),
#         (-32, -30): (-35, 48.9586),
#         (-30, -28): (-35, 51.6945),
#         (-28, -26): (-35, 54.2121),
#         (-26, -24): (-35, 56.5487),
#         (-24, -22): (-35, 58.7332),
#         (-22, 0): (-35, 60),
#         (0, 46): (-52.5, 60),
#         (46, 56): (-37.5, 60),
#         (56, 65): (-30, 60)
#     }
#     for decRange in horizonBox:
#         if decRange[0] < dec <= decRange[1]:  # man this is miserable
#             finalDecRange = horizonBox[decRange]
#             return tuple([Angle(finalDecRange[0], unit=u.deg), Angle(finalDecRange[1], unit=u.deg)])
#     return None
