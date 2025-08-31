# Sage Santomenna 2023
import os.path
from os.path import join, dirname
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir)))
from .constants import CACHE_PATH, CACHE_DB_PATH
sys.path.remove(os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir)))
import logging
import sqlite3
import time
from datetime import datetime, timedelta
from collections import namedtuple
import astropy
import math
import numpy as np
import numpy.typing as npt
import pytz
from astroplan.scheduling import ObservingBlock
from photometrics.mpc_neo_confirm import MPCNeoConfirm as mpc, MPC_GET_URL, MPC_POST_URL, MPC_HOSTNAME
from dataclasses import dataclass
from astropy import units as u
import asyncio 
import matplotlib.pyplot as plt
from numpy import sqrt

from alora.maestro.scheduleLib import schedule

try:
    grandparentDir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir))
    sys.path.append(grandparentDir)
    from alora.maestro.scheduleLib import asyncUtils
    from alora.maestro.scheduleLib import genUtils
    from alora.maestro.scheduleLib.candidateDatabase import Candidate, CandidateDatabase
    from alora.maestro.scheduleLib.genUtils import angleToHMSString, angleToDMSString

    sys.path.remove(grandparentDir)
    aConfig = genUtils.Config(os.path.join(grandparentDir, "files", "configs", "async_config.toml"))

except:
    from alora.maestro.scheduleLib import asyncUtils
    from alora.maestro.scheduleLib import genUtils
    from alora.maestro.scheduleLib.candidateDatabase import Candidate, CandidateDatabase
    from alora.maestro.scheduleLib.genUtils import angleToHMSString, angleToDMSString
    aConfig = genUtils.Config(os.path.join("files", "configs", "async_config.toml"))


mConfig = genUtils.Config(join(dirname(__file__),"config.toml"))

EPHEM_LIFETIME_MINUTES = mConfig["EPHEM_LIFETIME_MINUTES"]
UNCERT_LIFETIME_MINUTES = mConfig["UNCERT_LIFETIME_MINUTES"]

mpcInst = mpc()
mpcInst.int = 3

HEAVY_LOGGING = aConfig["HEAVY_LOGGING"]
MAX_SIMULTANEOUS_REQUESTS = aConfig["MAX_SIMULTANEOUS_REQUESTS"]
ASYNC_REQUEST_DELAY_S = aConfig["ASYNC_REQUEST_DELAY_S"]
_asyncHelper = asyncUtils.AsyncHelper(followRedirects=True, max_simultaneous_requests=MAX_SIMULTANEOUS_REQUESTS, time_between_batches=ASYNC_REQUEST_DELAY_S, do_heavy_logging=HEAVY_LOGGING)

# for the uncertainty plots lol
BLACK = [0, 0, 0]
RED = [255, 0, 0]
GREEN = [0, 255, 0]
BLUE = [0, 0, 255]
ORANGE = [255, 191, 0]
PURPLE = [221, 160, 221]

def rootMeanSquared(vals):
    return sqrt(1 / len(vals) * sum([i ** 2 for i in vals]))

# this isn't terribly elegant
def _findExposure(magnitude, str=True):
    # Internal: match magnitude to exposure description for TMO
    magnitude = float(magnitude)
    if str:
        if magnitude <= 19.5:
            return "1.0|600.0"
        if magnitude <= 20.5:
            return "1.0|600.0"
        if magnitude <= 21.0:
            return "2.0|600.0"
        if magnitude <= 21.5:
            return "3.0|600.0"
        return "TOO DARK"

    else:
        if magnitude <= 19.5:
            return 1, 600
        if magnitude <= 20.5:
            return 1, 600
        if magnitude <= 21.0:
            return 2, 600
        if magnitude <= 21.5:
            return 3, 600
        return -1, -1


def isBlockCentered(block: ObservingBlock, candidate: Candidate, times: astropy.time.Time):
    """!
    return an array of bools indicating whether or not the block is centered around each of the times provided
    @return: array of bools
    """
    obsTimeOffsets = {300: 30, 600: 120, 1200: 300,
                      1800: 600}  # seconds of exposure: seconds that the observation can be offcenter

    expTime = timedelta(seconds=block.configuration["duration"])
    # this will fail if obs.duration is not 300, 600, 1200, or 1800 seconds:
    maxOffset = timedelta(seconds=obsTimeOffsets[expTime.seconds])
    bools = np.array([checkOffsetFromCenter(t, expTime, maxOffset) for t in times])
    # print(bools.shape)
    return bools


def checkOffsetFromCenter(startTime, duration, maxOffset):
    """!
    is the observation that starts at startTime less that maxOffset away from the nearest ten minute interval?
    @param startTime:
    @param duration:
    @param maxOffset:
    @return:
    """
    center = startTime.datetime + (duration / 2)
    roundCenter = genUtils.roundToTenMinutes(center)
    return abs(roundCenter - center) < maxOffset
    # abs(nearestTenMinutesToCenter-(start + (expTime/2))) must be less than maxOffset

def mpc_to_dt(mpc_time):
    # converts the astropy Time objects returned from MPCNeoConfirm to datetime objects
    mpc_time.format = "fits"
    mpc_time.out_subfmt = "date_hms"
    mpc_time.format = "iso"
    mpc_time.out_subfmt = "date_hm"
    inBetween = mpc_time.value
    return datetime.strptime(inBetween, "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC)

def timeFromEphem(ephem):
    """!
    Converts the time associated with the ephem to a UTC datetime.

    @param ephem: List containing an ephem object.
    @type ephem: list

    @return: The UTC datetime extracted from the ephem object.
    @rtype: datetime.datetime
    """
    ephem.start_dt.format = "fits"
    ephem.start_dt.out_subfmt = "date_hms"
    ephem.start_dt.format = "iso"
    ephem.start_dt.out_subfmt = "date_hm"
    inBetween = ephem.start_dt.value
    return datetime.strptime(inBetween, "%Y-%m-%d %H:%M").replace(tzinfo=pytz.UTC)


def candidateToScheduleLine(candidate: Candidate, filter_name: str, startDt, centerDt: datetime, friend, ROI_height, ROI_width, ROI_start_x, ROI_start_y, binning, spath: str, logger, name=None):
    """
    Convert a candidate to a scheduler line
    @param candidate: The candidate to convert
    @param filter_name: The name of the filter to observe in
    @param startDt: The time at which the observation starts
    @param centerDt: The time at which the observation is centered
    @param friend: UncertainEphemFriend object
    @param ROI_height: The height of the region of interest
    @param ROI_width: The width of the region of interest
    @param ROI_start_x: The x-coordinate of the region of interest
    @param ROI_start_y: The y-coordinate of the region of interest
    @param spath: optional. directory to save the ephemeris to
    @return: A scheduler line
    @rtype: str
    """
    
    c = candidate
    truncated = centerDt - timedelta(minutes=(centerDt.minute - 5))
    ephems = asyncio.run(friend.get_ephems([c.CandidateName], truncated, mpcInst, True))
    if not ephems or c.CandidateName not in ephems.keys() or ephems[c.CandidateName] is None:
        if spath is not None:
            path = spath + c.CandidateName + ".txt"
            if not os.path.exists(path):  # we already saved this same candidate (_1 vs _2)
                with open(path, "w+") as f:
                    f.write("Couldn't get ephemeris")
        return ""
    try:
        ephemObj = ephems[c.CandidateName]
        # there's an annoying edge case where the time we want an ephem for is after the last time in one ephem file and before the first time in another.
        # when we asked for an ephem, we used the truncated time 
        ephem = ephemObj.get(centerDt,scheduler_format=True)
        if ephem is None:
            ephem = ephemObj.get(truncated,scheduler_format=True)
        lineAtObs = ephem.split("|")
    except Exception as e:
        raise
        return f"Couldn't find ephem for candidate {c.CandidateName} for centering time {startDt.strftime('%Y-%m-%dT%H:%M:%S.000')} and start time {centerDt.strftime('%Y-%m-%dT%H:%M:%S.000')}"
    
    line_dict = {}
    line_dict["DateTime"] = startDt.strftime('%Y-%m-%dT%H:%M:%S.000')
    line_dict["Target"] = name or c.CandidateName
    line_dict["Move"] = 1
    line_dict["RA"] = lineAtObs[4]
    line_dict["Dec"] = lineAtObs[5]
    line_dict["ExposureTime"], line_dict["#Exposure"] = _findExposure(c.Magnitude).split("|")
    line_dict["Filter"] = filter_name
    line_dict["CandidateID"] = c.ID
    line_dict["ROIHeight"] = ROI_height
    line_dict["ROIWidth"] = ROI_width
    line_dict["ROIStartX"] = ROI_start_x
    line_dict["ROIStartY"] = ROI_start_y
    line_dict["BinningSize"] = binning
    line_dict["Description"] = "\""+ lineAtObs[-1] + "\""

    line = schedule.fill_schedule_line(line_dict)

    if spath is not None:
        ephemObj.write(spath, logger, filename=c.CandidateName+".txt", scheduler_format=True, format_only=True)
    return line


async def getCometList(asyncHelper):
    """!
    Get a list of the possible comets from the MPC NEO site
    """
    mpcCometURL = f"{MPC_HOSTNAME}/iau/NEO/pccp.txt"
    lines = (await asyncHelper.makeRequest("comets", mpcCometURL, soup=True))[1].text
    if not lines:
        print("No comets")
        return []
    names = [line.split(" ")[0] for line in lines.split("\n") if line]
    return names



# https://cheatography.com/brianallan/cheat-sheets/python-f-strings-number-formatting/
def _formatEphem(ephems, desig,move=1,bin2fits=0,guiding=1, offset=0):
    # Internal: take an object in the form returned from self.mpc.get_ephemeris() and convert each line to the scheduler format, before returning it in a dictionary of {startDt : line}
    ephemDict = {None: schedule.scheduleHeader()}
    if ephems is None:
        return None
    for i in ephems:
        date = genUtils.timeToString(i.start_dt, scheduler=True)
        target = desig
        coords = f"{round(i.RA.to_value('degree'),7)}|{round(i.Dec.to_value('degree'),7)}"
        vMag = i.Vmag
        # get the correct exposure string based on the vMag
        exposure = str(_findExposure(float(vMag)))

        dRa = round(i.dRA.to_value('arcsec/min'),2) 
        dDec = round(i.dDec.to_value('arcsec/min'),2) 

        # for the description, we need RA and Dec in sexagesimal
        # sexagesimal = (i[1].ra.to_string(unit=u.hour, sep=':'), i[1].dec.to_string(unit=u.degree, sep=":"))
        # the end of the scheduler line must have a description that looks like this

        # description = "\'MPC Asteroid " + target + ", UT: " + datetime.strftime(i.start_dt, "%H%M") + ", RA: " + \
            #           angleToHMSString(i.RA) + ", DEC: " + angleToDMSString(
            # i.Dec) + ", dRA: " + dRa + ", dDEC: " + dDec + "\'"

        description = f"MPC Asteroid {target}, UT: {i.start_dt.strftime('%H%M')}, RA: {angleToHMSString(i.RA)}, DEC: {angleToDMSString(i.Dec)}, dRA: {dRa}, dDEC: {dDec}"

        lineList = [date, "1", target, str(move), coords, exposure, "CLEAR", str(bin2fits), str(guiding), str(offset), description]
        expLine = "|".join(lineList)
        ephemDict[i.start_dt] = expLine
    return ephemDict

async def asyncMultiEphem(designations, when, minAltitudeLimit, mpcInst: mpc, asyncHelper: asyncUtils.AsyncHelper,
                          logger, autoFormat=False,
                          mpcPostURL=MPC_POST_URL, obsCode=654):
    """!
    Asynchronously retrieves and parses multiple ephemeris data for given designations.

   @param designations: A list of object designations.
   @type designations: List[str]
   @param when: The datetime indicating the time of the ephemeris.
   @type when: datetime.datetime
   @param minAltitudeLimit: The minimum altitude limit for observability.
   @type minAltitudeLimit: float
   @param mpcInst: An instance of the `mpc` class.
   @type mpcInst: mpc
   @param asyncHelper: An instance of the `asyncUtils.AsyncHelper` class.
   @type asyncHelper: asyncUtils.AsyncHelper
   @param logger: The logger object for logging purposes.
   @param autoFormat: (Optional) Indicates whether to automatically format the ephemeris data. Defaults to False.
   @type autoFormat: bool
   @param mpcPostURL: (Optional) The URL for the MPC ephemeris confirmation. Defaults to 'https://minorplanetcenter.net/cgi-bin/confirmeph2.cgi'.
   @type mpcPostURL: str
   @param obsCode: (Optional) The observatory code. Defaults to 654.
   @type obsCode: int

   @return: A dictionary containing the parsed ephemeris data for each designation.
   @rtype: Dict[str, List[Tuple[datetime.datetime, str, float, str, str, Any]]]
    """
    # logger.error("asyncMultiEphem calling asyncMultiEphemRequest")
    ephemResults, ephemDict = await asyncMultiEphemRequest(designations, when, minAltitudeLimit, mpcInst, asyncHelper,
                                                           logger, mpcPostURL, obsCode)
    designations = ephemResults.keys()
    # print(ephemResults,ephemDict)
    for designation in designations:
        # parse valid ephems
        ephem = ephemResults[designation][0]
        if ephem is None:
            print("No ephem for " + designation)
            logger.warning("No ephem for " + designation)
            ephemDict[designation] = None
            continue
        # logger.info(ephem)
        ephem = ephem.find_all('pre')
        if len(ephem) == 0:
            logger.warning("No pre tags for ephem " + designation)
            ephemDict[designation] = None
            continue

        ephem = ephem[0].contents
        numRecs = len(ephem)
        # print("Num recs:",numRecs)
        # get object coordinates
        if numRecs == 1:
            logger.warning('Target ' + designation + ' is not observable or it has no uncertainty information.')
        else:
            obsList = []
            ephem_entry_num = -1
            for i in range(0, numRecs - 3, 4):
                # get datetime, ra, dec, vmag and motion
                if i == 0:
                    obsRec = ephem[i].split('\n')[-1].replace('\n', '')

                else:
                    obsRec = ephem[i].replace('\n', '').replace('!', '').replace('*', '')

                if "... <suppressed> ..." in obsRec:
                    obsRec = obsRec.replace("... <suppressed> ...", '')
                # keep a running count of ephem entries
                ephem_entry_num += 1

                # parse obs_rec
                # sys.stdout.write("Parsing "+repr(obsRec))
                # sys.stdout.flush()
                if not obsRec.replace(" ", ""):
                    continue
                obsDatetime, coords, vMag, dRa, dDec = mpcInst._MPCNeoConfirm__parse_ephemeris(obsRec)
                # dRA and dDec come in arcsec/sec
                dRa = u.Quantity(dRa, unit=u.arcsec / u.second)
                dDec = u.Quantity(dDec, unit=u.arcsec / u.second)
                # sys.stdout.write("Parsed "+repr(obsRec))
                # sys.stdout.flush()
                deltaErr = None

                obsList.append(EphemLine(mpc_to_dt(obsDatetime), coords.ra, coords.dec, vMag, dRa, dDec))
            if autoFormat:
                obsList = _formatEphem(obsList, designation)
            ephemDict[designation] = obsList
    return ephemDict


async def asyncMultiEphemRequest(designations, when, minAltitudeLimit, mpcInst: mpc,
                                 asyncHelper: asyncUtils.AsyncHelper, logger,
                                 mpcPostURL=MPC_POST_URL, obsCode=654):
    """!
    Asynchronously retrieve ephemerides for multiple objects. Requires internet connection.
    @param designations: A list of designations (strings) of the targets to objects
    @param when: 'now', a datetime object representing the time for which the ephemeris should be generated, or a string in the format 'YYYY-MM-DDTHH:MM:SS'
    @param minAltitudeLimit: The lower altitude limit, below which ephemeris lines will not be generated
    @param mpcInst: An instance of the MPCNeoConfirm class from the (privileged) photometrics.mpc_neo_confirm module
    @param asyncHelper: An instance of the asyncHelper class
    @return: Result of query in _____ form
    """
    # print("USING ONLY ONE EPHEM IN LIST")
    # designations = ["P21UWGF"]

    designations = list(set(designations))  # filter for only unique desigs
    urls = [mpcPostURL] * len(designations)
    postContents = {}
    defaultPostParams = {'mb': '-30', 'mf': '30', 'dl': '-90', 'du': '+90', 'nl': '0', 'nu': '100', 'sort': 'd',
                         'W': 'j',
                         'obj': 'None', 'Parallax': '1', 'obscode': obsCode, 'long': '',
                         'lat': '', 'alt': '', 'int': mpcInst.int, 'start': None, 'raty': mpcInst.raty,
                         'mot': mpcInst.mot,
                         'dmot': mpcInst.dmot, 'out': mpcInst.out, 'sun': mpcInst.supress_output,
                         'oalt': str(minAltitudeLimit)
                         }
    start_at = 0

    now_dt = datetime.now(tz=pytz.UTC)

    if when != "now":
        # if we've been given a string, convert it to dt. Otherwise, assume we have a dt and carry on
        if isinstance(when, str):
            when = datetime.strptime(when, '%Y-%m-%dT%H:%M')
        when = when.replace(tzinfo=pytz.UTC)
        if now_dt < when:
            start_at = round((when - now_dt).total_seconds() / 3600.) + 1

    for objectName in designations:
        newPostContent = defaultPostParams.copy()
        newPostContent["start"] = start_at
        newPostContent["obj"] = objectName
        postContents[objectName] = newPostContent
    
    # print(postContents)
    # logger.error("async multi ephem request multi get")
    # logger.info("Requesting ephemeris for " + str(designations))
    # logger.info(f"postContents ({type(postContents)}) : {postContents}")
    # logger.info(f"urls: {urls}")
    ephemResults = await asyncHelper.multiGet(urls, designations, soup=True, postContent=list(postContents.values()))
    # logger.info("======= EPHEM RESULTS =======:" + str(ephemResults))
    ephemDict = {}
    failedList = []

    for designation in designations:
        if designation not in ephemResults.keys() or ephemResults[designation] is None:
            logger.debug("Request for ephemeris for candidate " + designation + " failed. Will retry.")
            failedList.append(designation)

    if len(failedList):
        logger.info("Retrying...")
        retryPost = [postContents[a] for a in failedList]
        # logger.error("ephem retry request")
        retryEphems = await asyncHelper.multiGet([mpcPostURL] * len(failedList), failedList, soup=True,
                                                 postContent=retryPost)
        # logger.info("retryEphems: " + str(retryEphems))
        for retryDesignation in failedList:
            if retryDesignation not in retryEphems.keys() or retryEphems[retryDesignation] is None:
                logger.info("Request for "+ retryDesignation + "failed on retry. Eliminating and moving on.")
                ephemDict[retryDesignation] = None
            else:
                ephemResults[retryDesignation] = retryEphems[retryDesignation]

    return ephemResults, ephemDict


strMonthDict = dict(
    zip(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], range(1, 13)))


def updatedStringToDatetime(updated):
    """!
    Convert the string from the "Updated" field of the MPC list to a datetime object
    @param updated: string
    @return: datetime
    """
    if not updated:
        return None
    updated = updated.split()[1:3]
    month = strMonthDict[updated[0][:3]]
    fractionalDay, integerDay = math.modf(float(updated[1]))
    year = datetime.today().year
    return datetime(year, month, int(integerDay)) + timedelta(days=fractionalDay)

def mpcCandidatesForTimeRange(obsStart, obsEnd, duration, dbConnection: CandidateDatabase):
    return dbConnection.candidatesForTimeRange(obsStart, obsEnd, duration, "MPC NEO")


@dataclass
class EphemLine:
    start_dt: datetime
    RA: float
    Dec: float
    Vmag: float
    dRA: u.Quantity
    dDec: u.Quantity


class UncertainEphemFriend:
    """ The UncertainEphemFriend is responsible for maintaining and retrieving ephemerides and uncertainties for NEO candidates. 
        All activities that require retrieving ephemerides or uncertainties should be done with an instance of this class to take advantage of the cache. """
    def __init__(self):
        os.makedirs(os.path.dirname(CACHE_DB_PATH),exist_ok=True)
        self.conn = None
        self.db = None
        self.ephem_cache_dir = os.path.join(CACHE_PATH,"ephems")
        self.uncertainty_cache_dir = os.path.join(CACHE_PATH,"uncertainties")
        self.ephem_lifetime_s = EPHEM_LIFETIME_MINUTES * 60
        self.uncert_lifetime_s = UNCERT_LIFETIME_MINUTES * 60

        # edit these to edit the schema of the tables in the cache database
        self._ephem_schema = {'desig': 'TEXT', 'start': 'REAL', 'end': 'REAL', 'generated': 'REAL', 'filepath': 'TEXT'}
        self._uncertain_schema = {'desig': 'TEXT', 'RMSE_RA': 'REAL', 'RMSE_Dec': 'REAL', 'color': 'TEXT', 'graph_filepath': 'TEXT', 'generated': 'REAL'}
        
        os.makedirs(self.ephem_cache_dir, exist_ok=True)
        os.makedirs(self.uncertainty_cache_dir, exist_ok=True)
        self.logger = logging.getLogger("UncertainEphemFriend")
        self._create_db(CACHE_DB_PATH)

    def _create_db(self, dbpath):
        """
        Internal. Create the database and tables for the cache
        """
        self.conn = sqlite3.connect(dbpath)

        self.db = self.conn.cursor()
        # check if the schema of the existing db is correct
        current_ephem_schema = {e[1]: e[2] for e in self.conn.execute("PRAGMA table_info(ephems)").fetchall()}
        if current_ephem_schema and current_ephem_schema != self._ephem_schema:
            # if it isn't, drop the table - we'll recreate it later
            self.logger.error(f"Ephemeris schema in cache database ({current_ephem_schema}) does not match expected schema ({self._ephem_schema}). Recreating.")
            self.db.executescript("DROP TABLE ephems;")
            self.conn.commit()

        current_uncert_schema = {e[1]: e[2] for e in self.conn.execute("PRAGMA table_info(uncertainties)").fetchall()}
        if current_uncert_schema and current_uncert_schema != self._uncertain_schema:
            self.logger.error(f"Uncertainty schema in cache database ({current_uncert_schema}) does not match expected schema ({self._uncertain_schema}). Recreating.")
            self.db.executescript("DROP TABLE uncertainties;")
            self.conn.commit()
        self.db.execute(f"CREATE TABLE IF NOT EXISTS ephems ({','.join([f'{k} {v}' for k,v in self._ephem_schema.items()])})")
        self.db.execute(f"CREATE TABLE IF NOT EXISTS uncertainties ({','.join([f'{k} {v}' for k,v in self._uncertain_schema.items()])})")
        self.conn.commit()
    
    def cleanup_cache(self):
        """Remove old ephems and uncertainties from the cache"""
        # ephems
        self.logger.info("Cleaning up old ephems and uncertainties from cache")
        self.db.execute("SELECT filepath FROM ephems WHERE generated < ?",(datetime.now(tz=pytz.UTC).timestamp()-self.ephem_lifetime_s,))
        ephems = self.db.fetchall()
        for e in ephems:
            try:
                os.remove(e[0])
                try:
                    os.remove(e[0]+".f")
                except Exception as e:
                    pass
            except FileNotFoundError:
                self.logger.error(f"Couldn't find file {e[0]} to delete!")
        self.db.execute("DELETE FROM ephems WHERE generated < ?",(datetime.now(tz=pytz.UTC).timestamp()-self.ephem_lifetime_s,))
        self.conn.commit()
        # uncertainties
        self.db.execute("SELECT graph_filepath FROM uncertainties WHERE generated < ?",(datetime.now(tz=pytz.UTC).timestamp()-self.ephem_lifetime_s,))
        uncertainties = self.db.fetchall()
        for unc in uncertainties:
            try:
                os.remove(unc[0])
            except FileNotFoundError:
                self.logger.error(f"Couldn't find file {unc[0]} to delete!")
                
        self.db.execute("DELETE FROM uncertainties WHERE generated < ?",(datetime.now(tz=pytz.UTC).timestamp()-self.ephem_lifetime_s,))
        self.conn.commit()
    
    def find_cached_ephem_path(self, desig, ephem_time):
        """Find the path to a cached ephem for a given designation and time. Returns None if no cached ephem is found."""
        self.db.execute("SELECT filepath FROM ephems WHERE desig=? AND start <= ? AND end >= ? AND generated - ? <= ? ORDER BY generated DESC",(desig,ephem_time.timestamp(),ephem_time.timestamp(),datetime.now(tz=pytz.UTC).timestamp(),self.ephem_lifetime_s))
        filepath = self.db.fetchone()
        if filepath is not None:
            return filepath[0]
        return None
    
    async def get_ephems(self, desigs, ephem_time,mpc_inst=mpcInst, obsCode=500):
        """Get ephemerides for a list of designations at a given time. Returns a dictionary of {desig: MpcEphem object}"""
        need_to_fetch = []
        ephems = {}
        for desig in desigs:
            filepath = self.find_cached_ephem_path(desig,ephem_time)
            temp_eph_time = ephem_time
            # this little bit prevents us from constantly fetching ephems for an object when the time requested lies after the last ephem in a file but before an ephem ten minutes later (the time resolution) thats in another file. happens more often than you may expect
            if filepath is None:
                temp_eph_time = genUtils.roundToTenMinutes(ephem_time + timedelta(minutes=5))
                filepath = self.find_cached_ephem_path(desig,temp_eph_time)
            if filepath is not None:
                ephem_time = temp_eph_time
                if os.path.exists(filepath):
                    self.logger.debug(f"Found cached ephem for {desig} at {os.sep.join(filepath.split(os.sep)[-3:])}")
                    # we have a cached ephem, let's read it
                    # TODO: should we just find the specific line here?????? or read in the whole file, make the MpcEphem object, and return it
                    ephems[desig] = MpcEphem.from_file(desig,filepath)
                    continue
                
                # uh oh! we found a filepath in the database but the file doesn't exist!
                self.logger.error(f"Couldn't find file {filepath} for cached ephem for {desig} at {ephem_time}, despite it being in the cache database. Removing from cache database and will fetch.")
                self.db.execute("DELETE FROM ephems WHERE filepath=?",(filepath[0],))
            else:
                # only log this message on the else clause. everything else should run if we reach this point, no else required
                self.logger.info(f"No cached ephem for {desig} at {ephem_time}. Will fetch.")
            # we don't have a cached ephem, let's get it
            need_to_fetch.append(desig)
        self.conn.commit()

        if len(need_to_fetch) > 0:
            eph = await asyncMultiEphem(need_to_fetch,ephem_time,0,mpc_inst,_asyncHelper,self.logger,obsCode=obsCode)
            if eph is None:
                self.logger.error(f"UncertainEphemFriend failed to get any ephems! {len(need_to_fetch)} ephems were needed at {ephem_time} but none were fetched.")
                return ephems
            # self.logger.debug("eph: "+str(eph))
            for desig in need_to_fetch:
                if eph is None or desig not in eph.keys() or eph[desig] is None:
                    self.logger.error(f"UncertainEphemFriend failed to get ephem for {desig} at {ephem_time}")
                    continue
                ephem = eph[desig]
                eph_inst = MpcEphem(desig,ephem)
                filepath = eph_inst.write(os.path.join(self.ephem_cache_dir,desig),self.logger)
                self.db.execute("INSERT INTO ephems (desig,start,end,generated,filepath) VALUES (?,?,?,?,?)",(desig,eph_inst.start_time.timestamp(),eph_inst.end_time.timestamp(),datetime.now(tz=pytz.UTC).timestamp(),filepath))
                ephems[desig] = eph_inst
            self.conn.commit()
            self.cleanup_cache()
        return ephems
    
    def find_cached_uncertainty(self, desig):
        self.db.execute("SELECT desig, RMSE_RA, RMSE_Dec, color, graph_filepath FROM uncertainties WHERE desig=? AND generated - ? <= ? ORDER BY generated DESC",(desig,datetime.now(tz=pytz.UTC).timestamp(),self.uncert_lifetime_s))
        res = self.db.fetchone()
        if res is not None:
            return MpcUncert(res[0],res[1],res[2],res[3],res[4])
        return None
    
    async def get_uncertainties(self, desigs, async_helper=_asyncHelper):
        """Get uncertainties for a list of designations. Returns a dictionary of {desig: MpcUncert object}"""
        self.logger.info(f"Getting uncertainties for {desigs}")
        need_to_fetch = []
        uncerts = {}
        for desig in desigs:
            uncert = self.find_cached_uncertainty(desig)
            if uncert is not None:
                self.logger.info(f"Found cached uncert for {desig}.")
                uncerts[desig] = uncert
                continue
            self.logger.info(f"No cached uncert for {desig}. Will fetch.")
            # we don't have a cached uncert, let's get it
            need_to_fetch.append(desig)

        if len(need_to_fetch) > 0:
            uncert_dict = await self._fetch_uncertainties(need_to_fetch,async_helper)
            if uncert_dict is None:
                self.logger.error(f"UncertainEphemFriend failed to get any uncertainties! {len(need_to_fetch)} uncertainties were needed but none were fetched.")
                return uncerts
            for desig in need_to_fetch:
                if uncert_dict is None or desig not in uncert_dict.keys() or uncert_dict[desig] is None:
                    self.logger.error(f"UncertainEphemFriend failed to get uncert for {desig}")
                    continue
                uncert_obj = uncert_dict[desig]
                self.db.execute("INSERT INTO uncertainties (desig,RMSE_RA,RMSE_Dec,color,graph_filepath, generated) VALUES (?,?,?,?,?,?)",(uncert_obj.desig, uncert_obj.RMSE_RA, uncert_obj.RMSE_Dec, uncert_obj.color, uncert_obj.graph_filepath, datetime.now(tz=pytz.UTC).timestamp()))
                uncerts[desig] = uncert_obj
            self.conn.commit()
            self.cleanup_cache()
        return uncerts
    
    async def _fetch_uncertainties(self, designations, async_helper):
        """Internal. Fetch uncertainties for a list of designations. Returns a dictionary of {desig: MpcUncert object}"""
        start_jd = genUtils.dt_to_jd(datetime.now(tz=pytz.UTC))
        # get version 2 of the uncertainties, if we can (Ext=VAR2)
        res = await async_helper.multiGet([f"{MPC_HOSTNAME}/cgi-bin/uncertaintymap.cgi?Obj={desig}&JD={start_jd}&Form=Y&Ext=VAR2" for desig in designations],designations,soup=True)
        
        no_good = [d for d in designations if d not in res.keys() or res[d] is None] # these desigs didn't have a VAR2 version, so we need to get the VAR version
        for desig, soup in res.items():
            if soup is None or soup[0] is None:
                continue
            # print("SOUP: ", soup[0])
            bodies = soup[0].find_all('body')
            for body in bodies:
                # print("BODY: ", body)
                if "There is no uncertainty-information" in body.text:
                    # print("NO GOOD: ", desig)
                    no_good.append(desig)
                    break
        if len(no_good) > 0:
            self.logger.info(f"No VAR2 for {len(no_good)} out of {len(designations)}: {no_good}. Getting VAR instead.")
            # print(f"No VAR2 for {len(no_good)} out of {len(designations)}: {no_good}. Getting VAR instead.")
            res_2 = await async_helper.multiGet([f"{MPC_HOSTNAME}/cgi-bin/uncertaintymap.cgi?Obj={desig}&JD={start_jd}&Form=Y&Ext=VAR" for desig in no_good],no_good,soup=True)
            res.update(res_2)
        else:
            self.logger.info(f"Got VAR2 for all {len(designations)} desigs.")
        # parse uncertainties
        uncerts = {}
        for desig, soup in res.items():
            if soup is None or soup[0] is None:
                self.logger.error(f"Couldn't get uncertainty for {desig} (soup is None)")
                continue
            soup = soup[0]
            for a in soup.findAll('a', href=True):
                a.extract()
            try:
                text = soup.findAll('pre')[0].get_text()
            except:
                self.logger.error(f"No pre tags for {desig}")
                uncerts[desig] = None
                continue

            colorPriorityDict = {1: "BLACK", 2: "RED", 3: "ORANGE", 4: "GREEN"}
            colorPriorityList = []
            colorList = []
            # find the color of the error points (indicated by the characters at the end of the line)
            textList = text.split("\n")[1:-1]
            for line in textList:
                color = GREEN  # green is default, change it if we find a relevant symbol at end
                colorPriorityList.append(4)
                if "!!" in line:
                    color = RED
                    colorPriorityList.append(2)
                elif "!" in line:
                    color = ORANGE
                    colorPriorityList.append(3)
                elif "***" in line:
                    color = BLACK
                    colorPriorityList.append(1)
                colorList.append(color)

            # determine what the highest priority color is among all the different error points
            highestPriority = min(colorPriorityList)  # use min because 1 is highest priority
            highestColor = colorPriorityDict[highestPriority]

            if highestColor == "BLACK":
                self.logger.info(f"{desig} is a near-approach!")

            textList = [a.replace("!", '').replace("+", '').replace("*", '') for a in textList]
            splitList = [[x for x in a.split(" ") if x] for a in textList if a]  # lol
            splitList = [a[0:2] for a in splitList]  # sometimes it will have weird stuff (like "MBA soln") at the end,
            #                                        but in my experience the numbers always come first, so we can just slice them
            raList = [int(a[0]) for a in splitList]
            decList = [int(a[1]) for a in splitList]
            if not raList or not decList:
                self.logger.warning(f"Uh oh, missing RA or Dec errors for target {desig}")
                self.logger.warning("list of text: " + str(textList))
                self.logger.warning("splitList: " + str(splitList))

            # calculate RMSE
            rmsRA = rootMeanSquared(raList)
            rmsDec = rootMeanSquared(decList)

            # recreate error plots
            fig, ax = plt.subplots()
            ax.invert_xaxis()
            plt.title(desig, fontsize=18)
            plt.suptitle("RMS: " + str(round(rmsRA, 3)) + ", " + str(round(rmsDec, 3)))
            ax.scatter(raList, decList, c=np.array(colorList) / 255.0)
            plt.errorbar(np.mean(raList), np.mean(decList), xerr=rmsRA, yerr=rmsDec)
            # plt.show()
            fpath = os.path.join(self.uncertainty_cache_dir, f"{desig}.png")
            plt.savefig(fpath)
            plt.close()

            uncerts[desig] = MpcUncert(desig, round(rmsRA, 2), round(rmsDec, 2), highestColor, fpath)
        return uncerts

class MpcEphem:
    """An object that represents a group of ephemeris for one object over some time period"""
    def __init__(self,desig, ephems, filepath=None, format_path=None):
        # ephems must be a list of objects that have attributes start_dt (datetime), RA (angle or degree float), Dec (Angle or degree float), Vmag (float), dRA (Quantity), dDec (Quantity)
        self.desig = desig
        # ephem_dict is a dict of {start_dt: EphemLine named tuples}:
        self.times = [eph.start_dt for eph in ephems]
        self.ephem_dict = dict(zip(self.times,[EphemLine(eph.start_dt,genUtils.ensureAngle(eph.RA),genUtils.ensureAngle(eph.Dec),eph.Vmag,eph.dRA,eph.dDec) for eph in ephems]))
        self.start_time = self.times[0]
        self.end_time = self.times[-1]
        self.filepath=filepath # this just keeps track of where the ephem THINKS its data is for convenience
        self.format_path=format_path

    def get(self,t, tolerance=None, scheduler_format=False):
        """Get the ephemeris for a given time. If the time is not in the ephemeris, return the closest time within tolerance, or None. If scheduler_format is True, return the scheduler-formatted string for the ephemeris."""
        if t in self.ephem_dict.keys():
            return self.ephem_dict[t] if not scheduler_format else _formatEphem([self.ephem_dict[t]],self.desig)[t]
        else:
            if t > self.start_time and t < self.end_time:
                # return the closest time
                m = min(self.times, key=lambda x: abs(x-t))
                if tolerance is None or abs(m-t) < tolerance:
                    return self.ephem_dict[m] if not scheduler_format else _formatEphem([self.ephem_dict[m]],self.desig)[m]
        return None
    
    def __repr__(self) -> str:
        return f"MpcEphem for {self.desig} from {self.start_time} to {self.end_time}"

    def get_first(self, scheduler_format=False):
        """Get the first (earliest) ephemeris line in the ephemeris. If scheduler_format is True, return the scheduler-formatted string for the ephemeris."""
        return self.ephem_dict[self.start_time] if not scheduler_format else _formatEphem([self.ephem_dict[self.start_time]],self.desig)[self.start_time]
    
    def get_last(self, scheduler_format=False):
        """Get the last (latest) ephemeris line in the ephemeris. If scheduler_format is True, return the scheduler-formatted string for the ephemeris."""
        return self.ephem_dict[self.end_time] if not scheduler_format else _formatEphem([self.ephem_dict[self.end_time]],self.desig)[self.end_time]

    def write(self, save_dir, logger, filename=None, scheduler_format=True, format_only=False):
        """Write the ephemeris to a file. Returns the path to the file. If scheduler_format is True, also write a scheduler-formatted file. If format_only is True, only write the scheduler-formatted file."""
        start = round(self.start_time.timestamp())
        end = round(self.end_time.timestamp())
        generated = round(datetime.now(tz=pytz.UTC).timestamp())
        filename = filename if filename is not None else f"{generated}_{start}_{end}.txt"
        os.makedirs(save_dir,exist_ok=True)
        filepath = os.path.join(save_dir,filename)
        if format_only and not scheduler_format:
            logger.warning("Programmer error: MpcEphem.write called with format_only=True but scheduler_format=False. No formatted file will be written.")
        if not format_only:
            with open(filepath,"w+") as f:
                for v in self.ephem_dict.values():
                    f.write(f"{v.start_dt.timestamp()},{round(v.RA.to_value('degree'),5)},{round(v.Dec.to_value('degree'),5)},{v.Vmag},{round(v.dRA.to_value('arcsec/min'),2) },{round(v.dDec.to_value('arcsec/min'),2)}\n")
        if scheduler_format:
            fpath = filepath if format_only else f"{filepath}.f"
            self.format_path = fpath
            formatted = _formatEphem(list(self.ephem_dict.values()),self.desig)
            with open(fpath,"w+") as f:
                for v in formatted.values():
                    f.write(v+"\n")
        return filepath

    @property
    def raw(self):
        """Return the raw ephemeris data as a list of EphemLine namedtuples."""
        return list(self.ephem_dict.values())

    @classmethod
    def from_file(cls,desig, filepath):
        """Create a MpcEphem object from a file. The file must be in the format generated by MpcEphem.write"""
        with open(filepath,"r") as f:
            lines = f.readlines()
        
        ephems = []
        for line in lines:
            start_dt, RA, Dec, Vmag, dRA, dDec = line.split(",")
            start_dt = datetime.fromtimestamp(float(start_dt),tz=pytz.UTC)
            RA, Dec, Vmag, dRA, dDec = float(RA), float(Dec), float(Vmag), float(dRA)*u.arcsec/u.min, float(dDec)*u.arcsec/u.min
            ephems.append(EphemLine(start_dt,RA,Dec,Vmag,dRA,dDec))
        return cls(desig,ephems,filepath=filepath)

class MpcUncert:
    """An object that represents the uncertainty data for a single object."""
    def __init__(self, desig, RMSE_RA, RMSE_Dec, color, graph_filepath=None):
        self.desig = desig
        self.RMSE_RA = RMSE_RA
        self.RMSE_Dec = RMSE_Dec
        self.color = color
        self.graph_filepath = graph_filepath
