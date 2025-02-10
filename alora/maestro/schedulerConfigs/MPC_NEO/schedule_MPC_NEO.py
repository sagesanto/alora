import sys, os
from os.path import join, dirname
import configparser
from datetime import datetime as datetime, timedelta

import astroplan
import astropy.units as u
import numpy
import numpy as np
from astropy.time import Time
import logging
import pytz

try:
    grandparentDir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir))
    sys.path.append(
        grandparentDir)
    from schedulerConfigs.MPC_NEO import mpcUtils
    from scheduleLib.candidateDatabase import CandidateDatabase
    from scheduleLib.genUtils import stringToTime, TypeConfiguration, Config
    sys.path.remove(grandparentDir)


except ImportError:
    from schedulerConfigs.MPC_NEO import mpcUtils
    from scheduleLib.candidateDatabase import CandidateDatabase
    from scheduleLib.genUtils import stringToTime, TypeConfiguration, Config

mConfig = Config(join(dirname(__file__),"config.toml"))


# mConfig = mConfig["DEFAULT"]
logger = logging.getLogger("MPC NEO Scheduler")

ROI_start_x, ROI_start_y = mConfig["ROI_start_x"], mConfig["ROI_start_y"]
ROI_height, ROI_width = mConfig["ROI_height"], mConfig["ROI_width"]
FILTER = mConfig["FILTER"]
binning = mConfig["binning"]

def reverseNonzeroRunInplace(arr):
    nonzeroIndices = np.nonzero(arr)[0]  # find the indices of non-zero elements
    arr[nonzeroIndices] = arr[nonzeroIndices[::-1]]  # reverse the non-zero run in-place
    return arr


class MpcConfig(TypeConfiguration):
    def __init__(self, scorer, priority, observer=None, maxMinutesWithoutFocus=70, numObs=2, minMinutesBetweenObs=35):
        self.scorer = scorer
        self.Priority = priority
        self.maxMinutesWithoutFocus = maxMinutesWithoutFocus  # max time, in minutes, that this object can be scheduled after the most recent focus loop
        self.numObs = numObs
        self.minMinutesBetweenObs = minMinutesBetweenObs  # minimum time, in minutes, between the start times of multiple observations of the same object
        self.timeResolution = None
        self.candidateDict = None
        self.designations = None
        self.friend = mpcUtils.UncertainEphemFriend()

    def selectCandidates(self, startTimeUTC: datetime, endTimeUTC: datetime, dbPath):
        dbConnection = CandidateDatabase(dbPath, "Night Obs Tool")
        candidates = [c for c in mpcUtils.mpcCandidatesForTimeRange(startTimeUTC, endTimeUTC, 1, dbConnection)]
        # print("Candidates:",candidates)
        self.designations = [c.CandidateName for c in candidates]
        self.candidateDict = zip(candidates, self.designations)
        return candidates

    def generateTransitionDict(self):
        objTransitionDict = {'default': mConfig["minutes_after_obs"] * 60 * u.second}
        for d in self.designations:
            objTransitionDict[("Focus", d)] = 0 * u.second
            objTransitionDict[("Unused Time", d)] = 0 * u.second
        return objTransitionDict

    def scoreRepeatObs(self, c, scoreLine, numPrev, currentTime):
        return reverseNonzeroRunInplace(scoreLine) * mConfig["repeat_obs_slope_coefficient"]

    def generateTypeConstraints(self):
        return None

    def generateSchedulerLine(self, row, targetName, candidateDict, spath):
        desig = targetName[:-2] if "_" in targetName else targetName # cut off the _1, _2 from repeat obs
        c = candidateDict[desig]
        startDt = stringToTime(row["Start Time (UTC)"]).replace(tzinfo=pytz.UTC)
        duration = timedelta(minutes=row["Duration (Minutes)"])
        center = startDt + duration / 2
        center += timedelta(seconds=60-center.second, microseconds=-center.microsecond) # round up
        return mpcUtils.candidateToScheduleLine(c, FILTER, startDt, center, self.friend, ROI_height, ROI_width, ROI_start_x, ROI_start_y, binning, spath, logger, name=targetName)


def linearDecrease(lenArr, x1, xIntercept):
    return (np.arange(lenArr) - xIntercept) * -1 / (xIntercept - x1)


class MPCScorer(astroplan.Scorer):
    def __init__(self, candidateDict, *args, **kwargs):
        self.candidateDict = candidateDict
        super(MPCScorer, self).__init__(*args, **kwargs)

    # this makes a score array over the entire schedule for all of the blocks and each Constraint in the .constraints of each block and in self.global_constraints.
    def create_score_array(self, time_resolution=1 * u.minute):
        start = self.schedule.start_time
        end = self.schedule.end_time
        times = astroplan.time_grid_from_range((start, end), time_resolution)
        scoreArray = numpy.ones(shape=(len(self.blocks), len(times)))
        for i, block in enumerate(self.blocks):
            desig = block.target.name
            candidate = self.candidateDict[desig]

            if block.constraints:
                for constraint in block.constraints:  # apply the observability window constraint
                    appliedScore = constraint(self.observer, block.target,
                                              times=times)
                    scoreArray[i] *= appliedScore  # scoreArray[i] is an array of len(times) items

                startIdx = int((Time(stringToTime(candidate.StartObservability)) - start) / time_resolution)
                endIdx = int((Time(stringToTime(candidate.EndObservability)) - start) / time_resolution)
                scoreArray[i] *= linearDecrease(len(times), startIdx, endIdx)

                # window = (stringToTime(candidate.EndObservability) - stringToTime(
                #     candidate.StartObservability)).total_seconds()
                # scoreArray[i] *= (round(block.duration.to_value(u.second) / window,
                #                         4))  # favor targets with short windows so that they get observed
                # scoreArray[i] *= (round(1 / block.duration.to_value(u.second),
                #                         4))  # favor targets with long windows so it's more likely they get 2 obs in
            scoreArray[i] *= 20/((float(candidate.Magnitude)*mConfig["mag_coeff"]))
        for constraint in self.global_constraints:  # constraints applied to all targets
            scoreArray *= constraint(self.observer, self.targets, times, grid_times_targets=True)
        return scoreArray


def getConfig(observer):
    # returns a TypeConfiguration object for targets of type "MPC NEO"
    configuration = MpcConfig(MPCScorer, mConfig["priority"], maxMinutesWithoutFocus=mConfig["max_minutes_without_focus"],numObs=mConfig["num_obs"],minMinutesBetweenObs=mConfig["min_minutes_between_obs"])

    return "MPC NEO", configuration
    # this config will only apply to candidates with CandidateType "MPC NEO"
