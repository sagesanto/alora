import configparser
from datetime import datetime as datetime, timedelta
import os, sys
import astropy.units as u
import pandas as pd

from os.path import pardir, join, abspath, dirname
MODULE_PATH = abspath(join(dirname(__file__), pardir, pardir))
def PATH_TO(fname:str): return join(MODULE_PATH,fname)

try:
    sys.path.append(MODULE_PATH)
    from scheduleLib.candidateDatabase import Candidate
    from scheduleLib.genUtils import stringToTime, TypeConfiguration
    from scheduleLib.schedule import generic_schedule_line
    import scheduleLib.genUtils as genUtils

    genConfig = genUtils.Config(join(MODULE_PATH, "files", "configs", "config.toml"))
    aConfig = genUtils.Config(join(dirname(__file__), "config.toml"))

except ImportError:
    from scheduleLib.candidateDatabase import Candidate
    from scheduleLib.genUtils import stringToTime, TypeConfiguration
    from scheduleLib.schedule import generic_schedule_line
    import scheduleLib.genUtils as genUtils

    genConfig = genUtils.Config(join("files", "configs", "config.toml"))
    aConfig = genUtils.Config(join(dirname(__file__), "config.toml"))

minutesAfterObs = aConfig["downtime_after_obs"]

MINUTES_BETWEEN_DATASETS = aConfig["minutes_between_datasets"]
INDIVIDUAL_DATASET_EXPTIME = aConfig["individual_dataset_exptime"]
INDIVIDUAL_DATASET_NUMEXP = aConfig["individual_dataset_numexp"]


def findExposure(magnitude, str=True):
    return 1*u.second, 3 * INDIVIDUAL_DATASET_NUMEXP * INDIVIDUAL_DATASET_EXPTIME + 2 * 60 * MINUTES_BETWEEN_DATASETS  # otherwise, it's asking for the full exposure time


class AstrophotographyConfig(TypeConfiguration):
    def __init__(self, scorer, maxMinutesWithoutFocus=30, numObs=1, minMinutesBetweenObs=0,downtimeMinutesAfterObs=0):
        super().__init__(scorer,maxMinutesWithoutFocus, numObs, minMinutesBetweenObs, downtimeMinutesAfterObs)
        self.timeResolution = None
        self.candidateDict = None
        self.designations = None
        self.name = "Astrophotography"

    def selectCandidates(self, startTimeUTC: datetime, endTimeUTC: datetime, dbPath):
        candidates = Candidate.dfToCandidates(pd.read_csv(PATH_TO(join("schedulerConfigs","Astrophotography","observable.csv"))))
        for c in candidates:
            c.ExposureTime, c.NumExposures = findExposure(c.Magnitude, str=False)
        viable = [c for c in candidates if c.isObservableBetween(startTimeUTC, endTimeUTC, 1)]
        # print("Astro targets:", viable)
        self.designations = [c.CandidateName for c in viable]
        return viable

    def generateSchedulerLine(self, row, targetName, candidateDict, spath):
        c = candidateDict[targetName]
        c.ExposureTime = INDIVIDUAL_DATASET_EXPTIME*u.second
        c.NumExposures = INDIVIDUAL_DATASET_NUMEXP
        individualDuration = timedelta(seconds=INDIVIDUAL_DATASET_EXPTIME * INDIVIDUAL_DATASET_NUMEXP)
        firstStartDt = stringToTime(row["Start Time (UTC)"])
        minBetween = timedelta(minutes=MINUTES_BETWEEN_DATASETS)
        secondStartDt = firstStartDt + individualDuration + minBetween
        thirdStartDt = secondStartDt + individualDuration + minBetween
        lines = []
        move = 1  # we want the first one to have the telescope move and the other ones to stay still
        for filt, time in zip(["g", "i", "r"], [firstStartDt, secondStartDt, thirdStartDt]):
            name = targetName + "_" + filt + "_aphot"
            lines.append(generic_schedule_line(c.RA, c.Dec, filt, time, name.replace(" ", "_"),
                                             "{}: {}s by {}, {}".format(targetName, INDIVIDUAL_DATASET_EXPTIME,
                                                                        INDIVIDUAL_DATASET_NUMEXP, filt), INDIVIDUAL_DATASET_EXPTIME, INDIVIDUAL_DATASET_NUMEXP, move=bool(move),
                                             guiding=True))
            move = 0
        return lines

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


scheduling_config = AstrophotographyConfig(None, maxMinutesWithoutFocus=aConfig["max_minutes_without_focus"],numObs=aConfig["num_obs"],minMinutesBetweenObs=aConfig["min_minutes_between_obs"],downtimeMinutesAfterObs=aConfig["downtime_after_obs"])