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
    from scheduleLib.genUtils import stringToTime, TypeConfiguration, genericScheduleLine

    genConfig = configparser.ConfigParser()
    genConfig.read(join(MODULE_PATH, "files", "configs", "config.txt"))
    aConfig = configparser.ConfigParser()
    aConfig.read(join(MODULE_PATH, "files", "configs", "aphot_config.txt"))
except ImportError:
    from scheduleLib.candidateDatabase import Candidate
    from scheduleLib.genUtils import stringToTime, TypeConfiguration, genericScheduleLine
    genConfig = configparser.ConfigParser()
    genConfig.read(join("files", "configs", "config.txt"))
    aConfig = configparser.ConfigParser()
    aConfig.read(join("files", "configs", "aphot_config.txt"))

genConfig = genConfig["DEFAULT"]
aConfig = aConfig["DEFAULT"]

minutesAfterObs = aConfig.getint("minutes_after_obs")

MINUTES_BETWEEN_DATASETS = aConfig.getint("minutes_between_datasets")
INDIVIDUAL_DATASET_EXPTIME = aConfig.getfloat("individual_dataset_exptime")
INDIVIDUAL_DATASET_NUMEXP = aConfig.getint("individual_dataset_numexp")


def findExposure(magnitude, str=True):
    return 1, 3 * INDIVIDUAL_DATASET_NUMEXP * INDIVIDUAL_DATASET_EXPTIME + 2 * 60 * MINUTES_BETWEEN_DATASETS  # otherwise, it's asking for the full exposure time


class AstrophotographyConfig(TypeConfiguration):
    def __init__(self, scorer, observer, maxMinutesWithoutFocus=30, numObs=1, minMinutesBetweenObs=0):
        self.scorer = scorer
        self.maxMinutesWithoutFocus = maxMinutesWithoutFocus  # max time, in minutes, that this object can be scheduled after the most recent focus loop
        self.numObs = numObs
        self.minMinutesBetweenObs = minMinutesBetweenObs  # minimum time, in minutes, between the start times of multiple observations of the same object
        self.timeResolution = None
        self.candidateDict = None
        self.designations = None

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
        c.ExposureTime = INDIVIDUAL_DATASET_EXPTIME
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
            lines.append(genericScheduleLine(c.RA, c.Dec, filt, time, name.replace(" ", "_"),
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


def getConfig(observer):
    # returns a TypeConfiguration object for targets of type "Astrophotography"
    # this config will only apply to candidates with CandidateType "Astrophotography"
    return "Astrophotography", AstrophotographyConfig(None, observer, maxMinutesWithoutFocus=aConfig.getint("max_minutes_without_focus"),numObs=aConfig.getint("num_obs"),minMinutesBetweenObs=aConfig.getfloat("min_minutes_between_obs"))


if __name__ == "__main__":
    df = pd.read_csv("astroRes.csv")
    print(df)
    print(df.columns)
