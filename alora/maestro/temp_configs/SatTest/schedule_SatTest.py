import configparser
from datetime import datetime as datetime, timedelta
import os, sys
import astropy.units as u
import pandas as pd
from os.path import join, abspath, dirname, pardir
import tomli
from pytz import UTC
import re
try:
    grandparentDir = abspath(join(dirname(__file__), pardir, pardir))
    sys.path.append(grandparentDir)
    from scheduleLib.candidateDatabase import Candidate, CandidateDatabase
    from scheduleLib.genUtils import stringToTime, TypeConfiguration, genericScheduleLine

    sys.path.remove(grandparentDir)
    genConfig = configparser.ConfigParser()
    genConfig.read(join(grandparentDir, "files", "configs", "config.txt"))
    with open(join(grandparentDir, "files", "configs", "sattest.toml"),"rb") as f:
        s_config = tomli.load(f)
except ImportError:
    from scheduleLib.candidateDatabase import Candidate, CandidateDatabase
    from scheduleLib.genUtils import stringToTime, TypeConfiguration, genericScheduleLine
    genConfig = configparser.ConfigParser()
    genConfig.read(join("files", "configs", "config.txt"))
    with open(join("files", "configs", "sattest.toml"),"rb") as f:
        s_config = tomli.load(f)

genConfig = genConfig["DEFAULT"]

minutesAfterObs = s_config["DOWNTIME_MINUTES"]

MINUTES_BETWEEN_DATASETS = s_config["SPACING_MINUTES"]
NUM_OBS = s_config["RUNS"]
SAT_PY = s_config["SAT_PYTHON_PATH"]
SAT_SCRIPT = s_config["SAT_SCRIPT_PATH"]
SATELLITE = s_config["SATELLITE"]


class SatTestConfig(TypeConfiguration):
    def __init__(self, scorer, observer, maxMinutesWithoutFocus=30, numObs=1, minMinutesBetweenObs=0):
        self.scorer = scorer
        self.maxMinutesWithoutFocus = maxMinutesWithoutFocus  # max time, in minutes, that this object can be scheduled after the most recent focus loop
        self.numObs = numObs
        self.minMinutesBetweenObs = minMinutesBetweenObs  # minimum time, in minutes, between the start times of multiple observations of the same object
        self.timeResolution = None
        self.candidateDict = None
        self.designations = None

    def selectCandidates(self, startTimeUTC: datetime, endTimeUTC: datetime, dbPath):
        dbConnection = CandidateDatabase(dbPath, "SatTest Scheduling Agent")
        candidates = dbConnection.candidatesForTimeRange(startTimeUTC, endTimeUTC, 0.1, "SatTest")
        self.designations = [c.CandidateName for c in candidates]
        return candidates

    def generateSchedulerLine(self, row, targetName, candidateDict, spath):
        num = re.findall(r"_\d*$",targetName)
        if num:
            targetName = targetName.strip(num[0])
        c = candidateDict[targetName]
        time = stringToTime(row["Start Time (UTC)"])
        move = 1  # we want the first one to have the telescope move and the other ones to stay still
        outpath = join(s_config["OUTBASE"], datetime.now(tz=UTC).strftime("%Y%m%d"))
        return genericScheduleLine(0.0, 0.0, "CLEAR", time, "External_Single", f"{SAT_PY} {SAT_SCRIPT} '{SATELLITE}' '{outpath}'", 0,0, move=bool(move),guiding=True)

    def generateTypeConstraints(self):
        return None  # do we want stuff here?

    def generateTransitionDict(self):
        objTransitionDict = {'default': minutesAfterObs * 60 * u.second}
        for d in self.designations:
            objTransitionDict[("Focus", d)] = 0 * u.second
            objTransitionDict[("Unused Time", d)] = 0 * u.second
        return objTransitionDict

    def scoreRepeatObs(self, c, scoreLine, numPrev, currentTime):
        return scoreLine


def getConfig(observer):
    # returns a TypeConfiguration object for targets of type "SatTest"
    # this config will only apply to candidates with CandidateType "SatTest"
    return "SatTest", SatTestConfig(None, observer, maxMinutesWithoutFocus=s_config["MAX_MINUTES_WITHOUT_FOCUS"],numObs=s_config["RUNS"],minMinutesBetweenObs=s_config["SPACING_MINUTES"])
