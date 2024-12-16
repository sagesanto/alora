# Sage Santomenna 2024
# utilities for observing. many of these are poorly written - it's mostly just a collection of functions that i've found useful in the past.

import math
from astral import sun
from astral import LocationInfo

import pandas as pd
import numpy as np
from astropy.coordinates import Angle
from astropy import units as u
from astropy.io.votable import parse
from astropy.io import ascii
from astropy.table import Table
from astropy.coordinates import SkyCoord
from datetime import datetime, timedelta, timezone
#from datetime import UTC as dtUTC 
from astropy.time import Time
import pytz
from pytz import UTC as dtUTC
from astropy.coordinates import angular_separation


# dec_vertices = [item for key in horizonBox.keys() for item in key]  # this is just a list of integers, each being one member of one

sidereal_rate = 360 / (23 * 3600 + 56 * 60 + 4.091)  # deg/second

def ang_sep(c1, c2): return angular_separation(c1.ra, c1.dec, c2.ra, c2.dec)

def current_dt_utc():
    return datetime.utcnow().replace(tzinfo=dtUTC)
   # return datetime.now(dtUTC)

def file_timestamp():
    return current_dt_utc().strftime("%Y%m%d_%H_%M")

def get_current_sidereal_time(locationInfo):
    now = current_dt_utc().replace(second=0, microsecond=0)
    return Time(now).sidereal_time('mean', longitude=locationInfo.longitude)

def get_sunrise_sunset(locationInfo, dt=current_dt_utc(), jd=False):
    """!
    get sunrise and sunset for given location at given time
    @return: sunriseUTC, sunsetUTC
    @rtype: datetime.datetime
    """
    dt = dt.astimezone(timezone.utc)
    s = sun.sun(locationInfo.observer, date=dt, tzinfo=timezone.utc)
    sunriseUTC = s["sunrise"]
    sunsetUTC = sun.time_at_elevation(locationInfo.observer, -10, direction=sun.SunDirection.SETTING, date=dt)

    # TODO: make this less questionable - it probably doesn't do exactly what i want it to when run at certain times of the day:
    if sunriseUTC < dt:  # if the sunrise we found is earlier than the current time, add one day to it (approximation ofc)
        sunriseUTC = sunriseUTC + timedelta(days=1)

    if sunsetUTC > sunriseUTC:
        sunsetUTC = sunsetUTC - timedelta(days=1)

    if jd:
        sunriseUTC, sunsetUTC = dt_to_jd(sunriseUTC), dt_to_jd(sunsetUTC)
    return sunriseUTC, sunsetUTC

# tmo observability functions (from maestro)
def siderealToDate(siderealAngle: Angle, current_sidereal_time: Angle):
    """!
    Convert an angle representing a sidereal time to UTC by relating it to local sidereal time
    @param siderealAngle: astropy Angle
    @param current_sidereal_time: the current sidereal time, also an astropy angle
    @return: datetime object, utc
    """
    # ---convert from sidereal to UTC---
    # find the difference between the sidereal observability start time and the sidereal start time of the program
    siderealFromStart = siderealAngle - current_sidereal_time
    # add that offset to the utc start time of the program (we know siderealStart is local sidereal time at startTime, so we use it as our reference)
    timeUTC = current_dt_utc() + timedelta(
        hours=siderealFromStart.hour / 1.0027)  # one solar hour is 1.0027 sidereal hours

    return timeUTC.replace(tzinfo=pytz.UTC)


def dateToSidereal(dt: datetime, current_sidereal_time):
    """Apply an offset to get a sidereal time from a datetime object, using the current sidereal time as a reference. Assumes the current sidereal time is, in fact, current."""
    timeDiff = dt.astimezone(dtUTC) - current_dt_utc()
    sidereal_factor = 1.0027
    st = current_sidereal_time + Angle(str(timeDiff.total_seconds() * sidereal_factor / 3600) + "h")
    # st = st.wrap_at(360 * u.deg)
    return st


# def toDecimal(angle: Angle):
#     """!
#     Return the decimal degree representation of an astropy Angle, as a float
#     @return: Decimal degree representation, float
#     """
#     return round(float(angle.degree), 6)  # ew


def ensureFloat(angle):
    """!
    Return angle as a float, converting if necessary
    @r`type` angle: float, Angle
    @return: decimal angle, as a float
    """
    try:
        if isinstance(angle, str) or isinstance(angle, tuple):
            angle = Angle(angle)
            return ensureFloat(angle)  # lol
    except:
        pass
    if isinstance(angle, float):
        return angle
    if isinstance(angle,u.Quantity):
        return angle.to_value("degree")
    # if isinstance(angle, Angle):
    #     return toDecimal(angle)
    else:
        return float(angle)


def ensureAngle(angle):
    """!
    Return angle as an astropy Angle, converting if necessary
    @param angle: float, int, hms Sexagesimal string, hms tuple, or astropy Angle
    @return: angle, as an astropy Angle
    """
    if not isinstance(angle, Angle):
        try:
            if isinstance(angle, str) or isinstance(angle, tuple):
                angle = Angle(angle)
            else:
                angle = Angle(angle, unit=u.deg)
        except Exception as err:
            print("Error converting", angle, "to angle")
            raise err
    return angle


def angleToTimedelta(angle: Angle):  # low precision
    """!
    Convert an astropy Angle to an timedelta whose duration matches the hourangle of the angle
    @rtype: timedelta
    """
    angleTime = angle.to(u.hourangle)
    angleHours, angleMinutes, angleSeconds = angleTime.hms
    return timedelta(hours=angleHours, minutes=angleMinutes, seconds=0)


def find_transit_time(RA: Angle, location, target_dt=None, current_sidereal_time=None):
    """!Calculate the transit time of an object at the given location.

    @param RA: The right ascension of the object as an astropy Angle
    @type RA: Angle
    @param location: The observatory location.
    @type location: astral.LocationInfo
    @param target_dt: find the next transit after this time. if None, uses currentTime
    @param current_sidereal_time: the current sidereal time, as an astropy angle. will be calculated (slow) if not provided
    @return: The transit time of the object as a datetime object.
    @rtype: datetime.datetime
    """
    currentTime = current_dt_utc().replace(second=0, microsecond=0)
    if current_sidereal_time is None:
        lst = Time(currentTime).sidereal_time('mean', longitude=location.longitude)
    else:
        lst = current_sidereal_time
    target_time = target_dt.replace(second=0, microsecond=0) if target_dt else currentTime
    target_sidereal_time = dateToSidereal(target_time, lst)
    ha = Angle(wrap_around((RA - target_sidereal_time).deg), unit=u.deg)
    transitTime = target_time + angleToTimedelta(ha)
    # transitTime = transitTime.replace(tzinfo=pytz.UTC) # this is bad
    return transitTime

def wrap_around(value):
    a = -180
    b = 180
    return (value - a) % (b - a) + a

def get_angle(point1, point2, centroid):
    """ Find the interior angle of point1-centroid-point2"""
    angle1 = math.atan2(point1[1] - centroid[1], point1[0] - centroid[0])
    angle2 = math.atan2(point2[1] - centroid[1], point2[0] - centroid[0])
    return angle1 - angle2

def get_centroid(points):
    x, y = zip(*points)
    centroid_x = sum(x) / len(points)
    centroid_y = sum(y) / len(points)
    return centroid_x, centroid_y

# get hour angle as an Angle
def get_hour_angle(ra:Angle, dt, current_sidereal_time):
    sidereal = dateToSidereal(dt, current_sidereal_time)
    # print(sidereal, ra)
    return Angle(wrap_around((sidereal - ensureAngle(ra)).deg), unit=u.deg)


def jd_to_dt(hjd):
    time = Time(hjd, format='jd', scale='tdb')
    return time.to_datetime().replace(tzinfo=pytz.UTC)


def dt_to_jd(datetime):
    return Time(datetime).jd


# def observationViable(dt: datetime, ra: Angle, dec: Angle, current_sidereal_time=None,locationInfo=None):
#     """
#     Can a target with RA ra and Dec dec be observed at time dt? Checks hour angle limits based on TMO bounding box.
#     @return: bool
#     """
#     if current_sidereal_time is None:
#         current_sidereal_time = Time(current_dt_utc()).sidereal_time('mean', longitude=locationInfo.longitude)
#     raWindow, rac = get_RA_window(current_sidereal_time,dt,dec,ra=ra)
#     # NOTE THE ORDER:
#     return rac.is_within_bounds(raWindow[0], raWindow[1])

