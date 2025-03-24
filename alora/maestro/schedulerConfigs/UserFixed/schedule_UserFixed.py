import configparser
from datetime import datetime as datetime, timedelta
import os, sys
from os.path import join, dirname
import astropy.units as u
import pandas as pd


try:
    grandparentDir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir))
    sys.path.append(grandparentDir)
    from scheduleLib import genUtils, candidateDatabase
    from scheduleLib.candidateDatabase import Candidate, CandidateDatabase
    from scheduleLib.genUtils import stringToTime, TypeConfiguration
    from scheduleLib.schedule import generic_schedule_line

    sys.path.remove(grandparentDir)

except ImportError:
    from scheduleLib import genUtils
    from scheduleLib.genUtils import stringToTime, TypeConfiguration
    from scheduleLib.schedule import generic_schedule_line
    from scheduleLib.candidateDatabase import Candidate, CandidateDatabase


uConfig = genUtils.Config(join(dirname(__file__), "config.toml"))


class User_Fixed_Config(TypeConfiguration):
    def __init__(self, scorer, maxMinutesWithoutFocus=30, numObs=1, minMinutesBetweenObs=0, downtimeMinutesAfterObs=0):
        super().__init__(scorer,maxMinutesWithoutFocus, numObs, minMinutesBetweenObs, downtimeMinutesAfterObs)
        self.timeResolution = None
        self.candidateDict = None
        self.designations = None
        self.name="UserFixed"

    def selectCandidates(self, startTimeUTC: datetime, endTimeUTC: datetime, dbPath):
        dbConnection = CandidateDatabase(dbPath, "Night Obs Tool - UserFixed Agent")
        candidates = dbConnection.candidatesForTimeRange(startTimeUTC, endTimeUTC, 0.1, "UserFixed")
        self.designations = [c.CandidateName for c in candidates]
        return candidates

    def generateSchedulerLine(self, row, targetName, candidateDict, spath):
        c = candidateDict[targetName]
        start = stringToTime(row["Start Time (UTC)"])
        name = targetName + "_" + c.Filter + "_user_fixed"
        return generic_schedule_line(c.RA, c.Dec, c.Filter, start, name.replace(" ", "_"),
                                   "{}: {}s by {}, {}".format(targetName, c.ExposureTime,
                                                              c.NumExposures, c.Filter), c.ExposureTime, c.NumExposures,
                                   move=True,
                                   guiding=bool(c.Guide), bin2fits=uConfig.getboolean("bin2fits"))

    def generateTypeConstraints(self):
        return None  # do we want stuff here?

    def generateTransitionDict(self):
        objTransitionDict = {'default': uConfig["downtime_after_obs"] * 60 * u.second}
        for d in self.designations:
            objTransitionDict[("Focus", d)] = 0 * u.second
            objTransitionDict[("Unused Time", d)] = 0 * u.second
        return objTransitionDict

    def scoreRepeatObs(self, c, scoreLine, numPrev, currentTime):
        return scoreLine


scheduling_config = User_Fixed_Config(None, maxMinutesWithoutFocus=uConfig["max_minutes_without_focus"],downtimeMinutesAfterObs=uConfig["downtime_after_obs"])
