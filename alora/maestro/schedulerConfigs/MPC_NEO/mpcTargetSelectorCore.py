# Sage Santomenna 2023
import configparser
from datetime import datetime, timezone, timedelta
import sys, os
from os.path import join, dirname
# ---webtools
import httpx
# ---standard
import logging
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytz
from astral import LocationInfo
from astral import sun
from astropy.coordinates import Angle
import astropy.units as u
from astropy.time import Time
from bs4 import BeautifulSoup  # to parse html files
from numpy import sqrt
from photometrics.mpc_neo_confirm import MPCNeoConfirm as mpcObj

from schedulerConfigs.MPC_NEO import mpcUtils

# general fuckery
try:
    grandparentDir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir))
    sys.path.append(
        grandparentDir)
    from scheduleLib import genUtils, asyncUtils

    sys.path.remove(grandparentDir)
    genConfig = genUtils.Config(join(grandparentDir, "files", "configs", "config.toml"))
    aConfig = configparser.ConfigParser()
    aConfig.read(os.path.join(grandparentDir, "files", "configs", "async_config.txt"))

except ImportError:
    from scheduleLib import genUtils, asyncUtils

    genConfig = genUtils.Config(join("files", "configs", "config.toml"))
    aConfig = configparser.ConfigParser()
    aConfig.read(os.path.join("files", "configs", "async_config.txt"))

mConfig = genUtils.Config(join(dirname(__file__),"config.toml"))

aConfig = aConfig["DEFAULT"]

HEAVY_LOGGING = aConfig.getboolean("HEAVY_LOGGING")
MAX_SIMULTANEOUS_REQUESTS = aConfig.getint("MAX_SIMULTANEOUS_REQUESTS")
ASYNC_REQUEST_DELAY_S = aConfig.getfloat("ASYNC_REQUEST_DELAY_S")

utc = pytz.UTC

BLACK = [0, 0, 0]
RED = [255, 0, 0]
GREEN = [0, 255, 0]
BLUE = [0, 0, 255]
ORANGE = [255, 191, 0]
PURPLE = [221, 160, 221]


def remove_tags(html):
    # parse html content
    soup = BeautifulSoup(html, "html.parser")
    for data in soup(['style', 'script']):
        # Remove tags
        data.decompose()

    # return data by retrieving the tag content
    return ' '.join(soup.stripped_strings)


def rootMeanSquared(vals):
    return sqrt(1 / len(vals) * sum([i ** 2 for i in vals]))


class TargetSelector:
    def __init__(self, startTimeUTC="now", endTimeUTC="sunrise"):
        """!
        The TargetSelector, around which the MPC target selector is built
        @param startTimeUTC: The earliest start time for an observing window. Can be ``"now"``, ``"sunset"``, or of the form ``"%Y%m%d %H%M"``
        @param endTimeUTC: The latest time the last observation can end. Can be ``"sunrise"`` or of the form ``"%Y%m%d %H%M"``. *NOTE "sunrise" actually refers to the time one hour before sunrise. . .*
        """

        # set up the logger
        self.logger = logging.getLogger(__name__)

        # set location
        self.observatory = LocationInfo(name=genConfig["obs_name"], region=genConfig["obs_region"],
                                        timezone=genConfig["obs_timezone"],
                                        latitude=genConfig["obs_lat"],
                                        longitude=genConfig["obs_lon"])
        # find sunrise and sunset
        s = sun.sun(self.observatory.observer, date=datetime.now(timezone.utc), tzinfo=timezone.utc)
        self.sunriseUTC = s["sunrise"]

        now_dt = datetime.utcnow()
        now_dt = utc.localize(now_dt)

        if self.sunriseUTC < now_dt:  # if the sunrise we found is earlier than the current time, add one day to it (approximation ofc)
            self.sunriseUTC = self.sunriseUTC + timedelta(days=1)
        self.sunsetUTC = sun.time_at_elevation(self.observatory.observer, -10)

        # parse start time
        if startTimeUTC == "sunset":
            startTimeUTC = self.sunsetUTC
        elif startTimeUTC != 'now':
            startTime_dt = utc.localize(datetime.strptime(startTimeUTC, '%Y-%m-%d %H:%M'))
            if now_dt < startTime_dt:
                startTimeUTC = startTime_dt
            else:
                print('Observation date should be in future. Setting current date time')
        else:
            startTimeUTC = datetime.utcnow()

        startTimeUTC = utc.localize(startTimeUTC)

        # NOTE: the "sunrise" keyword is actually referring to our close time, which is one hour before sunrise
        if endTimeUTC == "sunrise":
            endTimeUTC = self.sunriseUTC - timedelta(hours=1)
        else:
            endTimeUTC = datetime.strptime(endTimeUTC, '%Y-%m-%d %H:%M')

        if startTimeUTC.tzinfo is None:
            startTimeUTC = utc.localize(startTimeUTC)
        self.startTime = startTimeUTC
        self.endTime = endTimeUTC
        self.siderealStart = Time(self.startTime, scale='utc').sidereal_time(kind="apparent",
                                                                             longitude=self.observatory.longitude)

        self.minHoursBeforeTransit = min(max(self.sunsetUTC - self.startTime, timedelta(hours=-2)),
                                         timedelta(hours=0)).total_seconds() / 3600
        self.maxHoursBeforeTransit = (self.endTime - self.startTime).total_seconds() / 3600

        # i open my wallet and it's full of blood
        mConfig["decMaxRMSE"]
        self.raMaxRMSE = mConfig["raMaxRMSE"]
        self.decMaxRMSE = mConfig["decMaxRMSE"]
        self.nObsMax = mConfig["nObsMax"]
        self.vMagMax = mConfig["vMagMax"]
        self.scoreMin = mConfig["scoreMin"]
        self.decMax = mConfig["decMax"]
        self.decMin = mConfig["decMin"]
        self.altitudeLimit = mConfig["altitudeLimit"]
        self.obsCode = mConfig["obsCode"]
        self.dRA_limits = [mConfig["dRA_min"], mConfig["dRA_max"]]
        self.dDec_limits = [mConfig["dDec_min"], mConfig["dDec_max"]]

        # init navtej's mpc retriever
        self.mpc = mpcObj()

        # for getting ephems
        self.friend = mpcUtils.UncertainEphemFriend()

        # init here, will use later
        self.objDf = pd.DataFrame(
            columns=["Temp_Desig", "Score", "Discovery_datetime", "R.A.", "Decl.", "V", "Updated", "Note", "NObs",
                     "Arc", "H",
                     "Not_Seen_dys"])
        self.mpcObjDict = {}
        self.filtDf = pd.DataFrame()

        # init web client for retrieving offsets
        # self.webClient = httpx.Client(follow_redirects=True, timeout=60.0)

        # init AsyncHelper
        self.asyncHelper = asyncUtils.AsyncHelper(followRedirects=True, max_simultaneous_requests=MAX_SIMULTANEOUS_REQUESTS, time_between_batches=ASYNC_REQUEST_DELAY_S, do_heavy_logging=HEAVY_LOGGING, timeout=240)

    def __del__(self):
        del self.asyncHelper
        self.killClients()

    def printSetupInfo(self):
        durationMinutes = round((self.endTime - self.startTime).total_seconds() / 60)
        formattedDuration = "{:02d}:{:02d}".format(durationMinutes // 60, durationMinutes % 60)
        print(f"Length of window: {formattedDuration} (h:m)")
        print("Starting at", self.startTime.strftime("%Y-%m-%d %H:%M"), "and ending at",
              self.endTime.strftime("%Y-%m-%d %H:%M"), "UTC")
        print("Allowing", self.minHoursBeforeTransit, "hours before transit and", self.maxHoursBeforeTransit,
              "hours after.")

    def getLocalSiderealTime(self, dt: datetime):
        """!
        Return the local sidereal time at time dt, as an angle
        @param dt: A datetime object
        @return: Sidereal time, as an astropy Angle
        """
        return Time(dt, scale='utc').sidereal_time(kind="apparent", longitude=self.observatory.longitude)

    @staticmethod
    def _convertMPC(obj):
        # Internal: convert a named tuple mpc object from navtej's code to lists that can be put in a df
        # RA comes in as decimal hours, we make it degrees by multiplying by 15
        l = [obj.designation, obj.score, obj.discovery_datetime, float(obj.ra)*15, obj.dec, obj.vmag, obj.updated, obj.note,
             obj.num_obs, obj.arc_length, obj.hmag, obj.not_seen_days]
        for i in range(len(l)):
            if l[i] == "":
                l[i] = None
        return l

    def timeUntilTransit(self, ra: float):
        """!
        Time until a target with an RA of ra transits (at the observatory)
        @return: Time until transit in hours, float
        """
        ra = Angle(str(ra) + "h")
        return (ra - self.siderealStart).hour

    # used only in the tool
    def makeMpcDataframe(self):
        """!
        Make a dataframe of MPC targets from the named tuples returned by self.mpc.neo_confirm_list. Store as self.objDf
        """
        self.mpc.get_neo_list()
        # this is a dictionary of designations to their mpcObjects
        for obj in self.mpc.neo_confirm_list:
            self.mpcObjDict[obj.designation] = obj
            targetList = TargetSelector._convertMPC(obj)
            newRow = dict(zip(self.objDf.columns, targetList))
            self.objDf.loc[len(self.objDf)] = newRow

    def pruneMpcDf(self):
        """!
        Filter self.objDf (populated by makeMpcDataframe) by magnitude, score, hour angle, declination, and number of observations
        """

        # calculate time until transit for each object
        self.objDf['TransitDiff'] = self.objDf.apply(lambda row: self.timeUntilTransit(row['R.A.']), axis=1)
        # original length of the dataframe
        original = len(self.objDf.index)
        print("Before pruning, we started with", original, "objects.")

        # establish the conditions for *excluding* a target
        conditions = [
            (self.objDf['Score'] < self.scoreMin),
            (self.objDf['V'] > self.vMagMax),
            (self.objDf['NObs'] > self.nObsMax),
            (self.objDf['TransitDiff'] < self.minHoursBeforeTransit) | (
                    self.objDf['TransitDiff'] > self.maxHoursBeforeTransit),
            (self.objDf['Decl.'] < self.decMin) | (self.objDf['Decl.'] > self.decMax)
        ]

        removedReasons = ["score", "magnitude", "nObs", "RA", "Declination"]

        # decide whether each target should be removed, and mark the reason why
        self.objDf["removed"] = np.select(conditions, removedReasons)
        # create a dataframe from only the targets not marked for removal
        self.filtDf = self.objDf.loc[(self.objDf["removed"] == "0")]

        for reason in removedReasons:
            print("Removed", len(self.objDf.loc[(self.objDf["removed"] == reason)].index), "targets because of their",
                  reason)

        print("In total, removed", original - len(self.filtDf.index), "targets.")
        print("\033[1;32mNumber of desirable targets found: " + str(len(self.filtDf.index)) + ' \033[0;0m')

        self.filtDf = self.filtDf.sort_values(by=["TransitDiff"], ascending=True)
        return

    def siderealToDate(self, siderealAngle: Angle):
        """!
        Convert an angle representing a sidereal time to UTC by relating it to local sidereal time
        @param siderealAngle: astropy Angle
        @return: datetime object, utc
        """
        # ---convert from sidereal to UTC---
        # find the difference between the sidereal observability start time and the sidereal start time of the program
        siderealFromStart = siderealAngle - self.siderealStart
        # add that offset to the utc start time of the program (we know siderealStart is local sidereal time at startTime, so we use it as our reference)
        timeUTC = self.startTime + timedelta(
            hours=siderealFromStart.hour / 1.0027)  # one solar hour is 1.0027 sidereal hours

        return timeUTC

    def dateToSidereal(self, dt: datetime):
        timeDiff = dt - self.startTime
        return self.siderealStart + Angle(str(timeDiff.total_seconds() / 3600) + "h")

    # def observationViable(self, dt: datetime, ra: Angle, dec: Angle):
    #     """
    #     Can a target with RA ra and Dec dec be observed at time dt? Checks hour angle limits.
    #     @return: bool
    #     """
    #     rac = ra.copy()
    #     hourAngleWindow = genUtils.get_hour_angle_limits(dec)
    #     if not hourAngleWindow: return False
    #     raWindow = [self.dateToSidereal(dt) - hourAngleWindow[1],
    #                 (self.dateToSidereal(dt) - hourAngleWindow[0]) % Angle(360, unit=u.deg)]

    #     # we want something like (23h to 17h) to look like [(23h to 24h) or (0h to 17h)] so we move the whole window to start at 0 instead
    #     if raWindow[0] > raWindow[1]:
    #         diff = Angle(24, unit=u.hour) - raWindow[0]
    #         raWindow[1] += diff
    #         rac = (rac + diff) % Angle(360, unit=u.deg)
    #         raWindow[0] = Angle(0, unit=u.deg)
    #     # print("Datetime:", dt)
    #     # print("Hour angle window:", hourAngleWindow)
    #     # print("RA window:", raWindow)
    #     # print("RA, dec:", ra, dec)
    #     # print("Is within bounds:", ra.is_within_bounds(raWindow[0], raWindow[1]))
    #     # NOTE THE ORDER:
    #     return rac.is_within_bounds(raWindow[0], raWindow[1])

    def isObservable(self, ephem_line):
        """
        Is observation described by ephemeris line observable?
        @param ephem: EphemLine
        @return: bool
        """
        # if self.decMin < ephem["dec"] < self.decMax:
        RA, dec = genUtils.ensureAngle(ephem_line.RA), genUtils.ensureAngle(ephem_line.Dec)
        # return self.observationViable(ephem_line.start_dt, RA, dec)
        return genUtils.observation_viable(ephem_line.start_dt,RA,dec)

    async def calculateObservability(self, desigs: list):
        """
        Calculate the start and end times of the observability window for an object by querying its ephemeris and clipping at sunrise/sunset
        @param desigs: list of designations of objects to be queried - must be valid MPC temp identifiers
        @returns: Dictionary {desig:(startDt,endDt)} or None
        """
        self.logger.info("Waiting on web requests...")
        # self.logger.error("target selector calculateObservability calling asyncMultiEphem")
        ephems = await self.friend.get_ephems(desigs, datetime.now(tz=pytz.UTC), self.mpc, obsCode=500)  # request for geocenter to get more output

        # print(f"ephems in calculateObservability: {ephems}")
        if ephems is None or len(ephems) == 0:
            self.logger.error("Couldn't get any ephems for any observability windows!")
            sys.stderr.write("Couldn't get any ephems for any observability windows!")
            return None

        good_desigs = [] # desigs for which we got at least one ephem
        need_more_ephems = [] # desigs for which we need more ephems (subset of good_desigs)
        windows = {}  # {desig:(startDt,endDt)}
        for desig in desigs:
            obsStart = False
            start = None
            end = None
            if desig not in ephems.keys() or ephems[desig] is None:
                self.logger.warning(
                    f"Couldn't get ephems and so can't calculate observability window for {desig}. Skipping.")
                # print("Couldn't get ephems and so can't calculate observability window for " + desig + ". Skipping.")
                windows[desig] = None
                continue
            good_desigs.append(desig)
            # ephems[desig] is an mpc ephem object. because we're adding more ephems to it, we need to get it as a list of EphemLine objects
            ephems[desig] = ephems[desig].raw
            # should already be sorted
            # ephems[desig].sort(key=lambda x: x.start_dt)
            assert all([ephems[desig][i].start_dt <= ephems[desig][i+1].start_dt for i in range(len(ephems[desig])-1)])
            if ephems[desig][-1].start_dt < datetime.now(tz=pytz.UTC) + timedelta(hours=mConfig["ephem_lookahead_hours"]):
                need_more_ephems.append(desig)
                continue

        while len(need_more_ephems) > 0:
            self.logger.info(f"Getting more ephems for {len(need_more_ephems)} targets.")
            earliest_end = min([ephems[desig][-1].start_dt+timedelta(minutes=1) for desig in need_more_ephems])
            more_eph = await self.friend.get_ephems(need_more_ephems, earliest_end, self.mpc, obsCode=500)
            for desig in need_more_ephems.copy():
                if desig not in more_eph.keys() or more_eph[desig] is None:
                    self.logger.warning(
                        f"Got some ephems but couldn't get more for {desig}")
                    need_more_ephems.remove(desig)
                    continue
                ephems[desig] = ephems[desig] + more_eph[desig].raw
                ephems[desig].sort(key=lambda x: x.start_dt)
                if ephems[desig][-1].start_dt >= datetime.now(tz=pytz.UTC) + timedelta(hours=mConfig["ephem_lookahead_hours"]):
                    need_more_ephems.remove(desig)
        self.logger.info(f"Done getting ephems.")

        for desig in good_desigs:
            obsStart = False
            start = None
            end = None
            for ephem in ephems[desig]:
                if self.isObservable(ephem):
                    if not obsStart:  # window begins
                        obsStart = True
                        start = ephem.start_dt
                elif obsStart:  # we've already started and we're no longer observable. window over
                    end = ephem.start_dt
                    windows[desig] = (start, end)
                    break
                end = ephem.start_dt  # this is the time of the last ephem we could get, so is the 'end' of our window (for now)
            if start is None:  # we've run through all the ephemeris. End the window here, if one was started. otherwise, return None
                self.logger.info(f"{desig} is not observable at all during the times we have ephemerides for.")
                # ha_start, ha_end = genUtils.getHourAngleLimits(ephems[desig][0].Dec)
                # print(f"RA window: {self.siderealStart + ha_start} to {self.siderealStart + ha_end}")
                # # print(f"current sidereal time: {self.siderealStart}")
                # print(f"RA: {ephems[desig][0].RA}")
                windows[desig] = None
                continue
            windows[desig] = (start, end)

        for desig in windows.keys():
            if windows[desig] is not None:
                if windows[desig][0] > windows[desig][1]:
                    raise ValueError(f"Critical problem. Observability window for {desig} is invalid: {windows[desig]}")
                self.logger.debug("Target " + desig + " is visible between " +
                                  windows[desig][0].strftime("%Y-%m-%d %H:%M") + " and " +
                                  windows[desig][1].strftime("%Y-%m-%d %H:%M"))
            else:
                self.logger.debug("Nominal: No valid observability window for target " + desig + ".")
        return windows

    def killClients(self):
        """
        Mandatory: close the internal clients
        """
        pass
        # self.webClient.close()

    def pruneByError(self):
        """
        Remove targets with rms values > acceptable from the running filtered dataframe
        """
        self.filtDf = self.filtDf.loc[self.filtDf['rmsRA'] <= self.raMaxRMSE & self.filtDf['rmsDec'] <= self.decMaxRMSE]
        # self.filtDf = self.filtDf.loc[self.filtDf['rmsDec'] <= self.decMaxRMSE]

    def saveCSVs(self, path):
        """
        Save csvs of the filtered and unfiltered targets to outputDir
        """
        self.filtDf.to_csv(path + "/Targets.csv")
        self.objDf.to_csv(path + "/All.csv")

    # basically deprecated, only used by mpcSelectorTool.py now
    async def fetchFilteredEphemerides(self):
        """
        Return the ephemerides of only targets that passed filtering. Note: must be called after filtering has been done to return anything meaningful
        @return: a Dictionary of {designation: {startTimeDt: formatted ephem line}}
        """
        # self.logger.error("fetch filtered ephemerides calling asyncMultiEphem")
        return await mpcUtils.asyncMultiEphem(list(self.filtDf.Temp_Desig), self.startTime, self.altitudeLimit,
                                              self.mpc, self.asyncHelper, self.logger, autoFormat=True)


# basically deprecated, only used by mpcSelectorTool.py now
def saveEphemerides(ephems, saveDir):
    """
    Save each set of ephemerides to the file [saveDir]/[desig]_ephems.txt
    @param ephems: The ephemerides to save, in {designation: {startTimeDt: ephemLine}} form
    @param saveDir: The directory to save to
    """
    for desig in ephems.keys():
        outFilename = saveDir + "/" + desig + "_ephems.txt"
        ephemLines = ephems[desig].values()
        with open(outFilename, "w") as f:
            f.write('\n'.join(ephemLines))
