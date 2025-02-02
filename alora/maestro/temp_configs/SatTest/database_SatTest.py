import configparser
import sys, os, pandas as pd
from datetime import datetime
import tomli
from os.path import join, abspath, dirname, pardir
from astral import LocationInfo
from astropy.time import Time
import pytz

try:
    grandparentDir = abspath(join(dirname(__file__), pardir, pardir))
    sys.path.append(
        grandparentDir)
    from scheduleLib import genUtils
    from scheduleLib.candidateDatabase import Candidate, CandidateDatabase

    sys.path.remove(grandparentDir)
    genConfig = configparser.ConfigParser()
    genConfig.read(join(grandparentDir, "files", "configs", "config.txt"))
    with open(join(grandparentDir, "files", "configs", "sattest.toml"),"rb") as f:
        s_config = tomli.load(f)
except ImportError:
    from scheduleLib import genUtils
    from scheduleLib.candidateDatabase import Candidate, CandidateDatabase

    genConfig = configparser.ConfigParser()
    genConfig.read(join("files", "configs", "config.txt"))
    with open(join("files", "configs", "sattest.toml"),"rb") as f:
        s_config = tomli.load(f)

genConfig = genConfig["DEFAULT"]

PRIORITY = s_config["PRIORITY"]

def evalObservability(candidates, location):
    sunrise, sunset = genUtils.get_sunrise_sunset(location)
    for c in candidates:
        c.StartObservability = genUtils.timeToString(sunset)
        c.EndObservability = genUtils.timeToString(sunrise)
    return candidates

def updateCandidate(candidate: Candidate, dbConnection: CandidateDatabase):
    dbConnection.editCandidateByID(candidate.ID, candidate.asDict())

def update_database(dbPath):
    logger = genUtils.configure_logger("SatTest")
    logger.info("Beginning update for SatTest")
    location = LocationInfo(name=genConfig["obs_name"], region=genConfig["obs_region"], timezone=genConfig["obs_timezone"],
                            latitude=genConfig.getfloat("obs_lat"),
                            longitude=genConfig.getfloat("obs_lon"))
    synodicStart = datetime.now(tz=pytz.UTC)

    dbConnection = CandidateDatabase(dbPath, "SatTest Database Agent")
    candidates = dbConnection.table_query("Candidates", "*",
                                          "RemovedReason IS NULL AND CandidateType IS \"SatTest\"",
                                          [], returnAsCandidates=True)
    found_cand = bool(candidates)
    if not candidates:
        c = Candidate(f"SatTest {s_config['SATELLITE']}","SatTest",RA=0,Dec=0,Priority=s_config["PRIORITY"],NumExposures=1,ExposureTime=s_config["DURATION"]*60)
        candidates = [c]
    if s_config["RUN"]:
        logger.info("Running sat test observability checks")
        candidates = evalObservability(candidates, location)
        for c in candidates:
            c.Priority = PRIORITY
            c.ApproachColor = "PURPLE"
            if c.hasField("ID"):
                updateCandidate(c,dbConnection)
            else:
                dbConnection.insertCandidate(c)
    else:
        if found_cand:
            logger.warning("Removing all sat test targets because SatTest config key 'RUN' is set to False")
            for c in candidates:
                dbConnection.removeCandidateByID(c.ID,reason="SatTest config RUN is set to false")
        else:
            logger.info("Not doing SatTest because SatTest config key 'RUN' is set to False")