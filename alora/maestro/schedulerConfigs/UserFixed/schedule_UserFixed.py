import configparser
from datetime import datetime as datetime, timedelta
import os, sys
import astropy.units as u
import pandas as pd


try:
    grandparentDir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir))
    sys.path.append(grandparentDir)
    from scheduleLib import genUtils, candidateDatabase
    from scheduleLib.candidateDatabase import Candidate, CandidateDatabase
    from scheduleLib.genUtils import stringToTime, TypeConfiguration, genericScheduleLine

    sys.path.remove(grandparentDir)
    uConfig = configparser.ConfigParser()
    uConfig.read(os.path.join(grandparentDir, "files", "configs", "userFixed_config.txt"))

except ImportError:
    from scheduleLib import genUtils
    from scheduleLib.genUtils import stringToTime, TypeConfiguration, genericScheduleLine
    from scheduleLib.candidateDatabase import Candidate, CandidateDatabase

    uConfig = configparser.ConfigParser()
    uConfig.read(os.path.join("files", "configs", "userFixed_config.txt"))


uConfig = uConfig["DEFAULT"]


class User_Fixed_Config(TypeConfiguration):
    def __init__(self, scorer, observer, maxMinutesWithoutFocus=30, numObs=1, minMinutesBetweenObs=0):
        self.scorer = scorer
        self.maxMinutesWithoutFocus = maxMinutesWithoutFocus  # max time, in minutes, that this object can be scheduled after the most recent focus loop
        self.numObs = numObs
        self.minMinutesBetweenObs = minMinutesBetweenObs  # minimum time, in minutes, between the start times of multiple observations of the same object
        self.timeResolution = None
        self.candidateDict = None
        self.designations = None

    def selectCandidates(self, startTimeUTC: datetime, endTimeUTC: datetime, dbPath):
        dbConnection = CandidateDatabase(dbPath, "Night Obs Tool - UserFixed Agent")
        candidates = dbConnection.candidatesForTimeRange(startTimeUTC, endTimeUTC, 0.1, "UserFixed")
        self.designations = [c.CandidateName for c in candidates]
        return candidates

    def generateSchedulerLine(self, row, targetName, candidateDict, spath):
        c = candidateDict[targetName]
        start = stringToTime(row["Start Time (UTC)"])
        name = targetName + "_" + c.Filter + "_user_fixed"
        return genericScheduleLine(c.RA, c.Dec, c.Filter, start, name.replace(" ", "_"),
                                   "{}: {}s by {}, {}".format(targetName, c.ExposureTime,
                                                              c.NumExposures, c.Filter), c.ExposureTime, c.NumExposures,
                                   move=True,
                                   guiding=bool(c.Guide), bin2fits=uConfig.getboolean("bin2fits"))

    def generateTypeConstraints(self):
        return None  # do we want stuff here?

    def generateTransitionDict(self):
        objTransitionDict = {'default': uConfig.getfloat("downtime_after_obs") * 60 * u.second}
        for d in self.designations:
            objTransitionDict[("Focus", d)] = 0 * u.second
            objTransitionDict[("Unused Time", d)] = 0 * u.second
        return objTransitionDict

    def scoreRepeatObs(self, c, scoreLine, numPrev, currentTime):
        return scoreLine


def getConfig(observer):
    # returns a TypeConfiguration object for targets of type "UserFixed"
    # this config will only apply to candidates with CandidateType "UserFixed"
    return "UserFixed", User_Fixed_Config(None, observer, maxMinutesWithoutFocus=uConfig.getint(
        "max_minutes_without_focus"))
