# Sage Santomenna 2023

# this is another attempt at a scheduler. this will use a ModularSchedule as a base, modify it with Operations using a
# monte carlo tree approach, and then convert it to an astroplan Schedule object. 
# for now, this largely consists of components lifted from the original scheduler and then modified a little. 

import configparser
import os, sys, time, re
# import timeit
# from line_profiler_pycharm import profile
# from pathlib import Path

# dirname = os.path.dirname(PyQt6.__file__)
# plugin_path = os.path.join(Path(__file__).parent, 'PyQt6', 'Qt6', 'plugins')
# os.environ['QT_PLUGIN_PATH'] = plugin_path
# os.environ['QT_DEBUG_PLUGINS']="1"
import copy
import json
import queue
import random
import shutil
from collections import Counter
from datetime import datetime, timedelta
from importlib import import_module
# import PyQt6

import astroplan.utils
import astropy.units as u
import numpy as np
import pandas as pd
import pytz
import seaborn as sns
from astroplan import Observer, TimeConstraint, FixedTarget, ObservingBlock, Transitioner
from astroplan.scheduling import Schedule
from astroplan.target import get_skycoord
from astropy.coordinates import EarthLocation
from astropy.coordinates import SkyCoord
from astropy.time import Time
import matplotlib
# matplotlib.use('TKAgg')  # very important
from matplotlib import pyplot as plt
from matplotlib.colors import ListedColormap

import scheduleLib.sCoreCondensed
from scheduleLib.candidateDatabase import Candidate
from scheduler import TMOScheduler

# for packaging reasons, i promise
try:
    sys.path.append(
        os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir)))

    from scheduleLib import genUtils
    from scheduleLib import sCoreCondensed
    from scheduleLib.genUtils import stringToTime, roundToTenMinutes

    genConfig = genUtils.Config(os.path.join(os.path.dirname(__file__), "files", "configs", "config.toml"))

    sys.path.remove(os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir)))
except ImportError:
    from scheduleLib import genUtils
    from scheduleLib import sCoreCondensed
    from scheduleLib.genUtils import stringToTime, roundToTenMinutes

    genConfig = genUtils.Config(os.path.join("files", "configs", "config.toml"))


utc = pytz.UTC


# new strategy: generate a legal but not necessarily optimal schedule, do monte carlo tree search to find optimal schedule.
# only allow "moves" that result in a legal schedule. 
# need to be able to quickly determine if a move results in a legal schedule.
#      need to be able to quickly determine if a schedule is legal.
# moves: swap two observations, delete an observation, add an observation
# need to be able to quickly score a schedule

# parts to develop
#1. legal schedule determination
#2. initial schedule creation - most of this is done by scheduler.py, just need to tweak to enforce repeat obs rules
#3. ability to apply a move to a schedule
#4. objective function for schedule
#5. creation of tree from a given schedule
#6. monte carlo tree search

#1. legality of a schedule (sCoreCondensed.py)
#a schedule is legal if:
# all observations are entirely between the start and end of the night
# no observations overlap
# all observations are wholly contained in their observability windows
# all observations run for their full duration
# all focus loops are entirely between the start and end of the night
# no focus loops overlap with each other or with observations
# all focus loops run for their full duration
# there is appropriate spacing between observations
# observations start and end within the required time of the last focus loop
# each observation is scheduled exactly 1 + (num repeat obs) times or not at all - NEED TO DO

#2. initial schedule creation (scheduler.py)
# this needs to be tweaked to schedule all of an object's observations when scheduling the first one
# this needs to be streamlined to be faster - doesn't need to be as worried about score as it is now, that will be refined by the tree search

def findCandidates(observer: Observer, startTime: datetime, endTime: datetime, blacklist, candidateDbPath: str):
    configDict = {}
    # import configurations from python files placed in the schedulerConfigs folder
    files = []
    for root, dir, file in os.walk("./schedulerConfigs"):
        files += [".".join([root.replace("./", "").replace("\\", ".").replace("/", "."), f[:-3]]) for f in file if
                  f.endswith(".py") and "schedule" in f]
    # maybe wrap this in a try?:
    for file in files:
        try:
            module = import_module(file, "schedulerConfigs")
            typeName, conf = module.getConfig(observer)  # modules must have this function
            configDict[typeName] = conf
        except:
            print("Can't import", file)
            raise

    # turn the lists of candidates into one list
    candidates = [candidate for candidateList in
                  [c.selectCandidates(startTime, endTime, candidateDbPath) for c in configDict.values()]
                  for candidate in
                  candidateList if
                  candidate.CandidateName not in blacklist]

    if len(candidates) == 0:
        sys.stdout.flush()
        raise ValueError("No candidates provided - nothing to schedule")
    
    return candidates, configDict
    

# take in an observer and some details, find all the candidates that are observable, and make the blocks and transitioner
def prepareToSchedule(candidates,configDict,whitelist):
    """!
    Do the actual scheduling
    @param observer: the Observer object representing the telescope's location
    @param blacklist: list of designations of targets to ban from being scheduled
    @param whitelist: list of designations of targets to give the highest priority
    @param excludedTimeRanges: list of tuples of times, in integer seconds since epoch, to forbid observations from being scheduled between
    @param temperature: 0-10. represents the randomness applied to scoring; 0 is deterministic
    @return a dataframe representing the schedule, the list of blocks, the schedule object, the dictionary of candidates, and the dictionary of config objects
    """

    # blocks are what will be slotted into the schedule - blocks specify a target but not a set start or end time
    blocks = {}  # blocks by priority
    for i, c in enumerate(candidates):
        c.Priority = c.Priority + 1 if c.CandidateName not in whitelist else 1  # ---- manage the whitelist -----
        if c.Priority not in blocks.keys():
            blocks[c.Priority] = []
        # c.RA = genUtils.ensureAngle(str(c.RA) + "h")
        # c.Dec = genUtils.ensureAngle(float(c.Dec))

    designations = [candidate.CandidateName for candidate in candidates]
    candidateDict = dict(zip(designations, candidates))

    # constraint on when the observation can *start*
    timeConstraintDict = {c.CandidateName: TimeConstraint(Time(stringToTime(c.StartObservability)),
                                                          Time(stringToTime(c.EndObservability) - timedelta(
                                                              seconds=float(c.NumExposures) * float(c.ExposureTime))))
                          for c in candidates}

    # make a dict of constraints to put on all targets of a given type (specified optionally by config py file)
    typeSpecificConstraints = {}
    for typeName, conf in configDict.items():
        typeSpecificConstraints[
            typeName] = conf.generateTypeConstraints()  # dictionary of {type of target: list of astroplan constraints, initialized}

    # --- create the blocks ---
    blocks = {}  # dictionary that stores targets grouped by priority level
    for c in candidates:
        exposureDuration = float(c.NumExposures) * float(c.ExposureTime)  # calculate block duration
        name = c.CandidateName
        specConstraints = typeSpecificConstraints[
            c.CandidateType]  # get constraints that should apply to targets of this type
        aggConstraints = [timeConstraintDict[name]]  # constraints that apply to all targets
        if specConstraints is not None:
            aggConstraints += specConstraints
        target = FixedTarget(coord=SkyCoord(ra=c.RA, dec=c.Dec),
                             name=name)  # create the underlying target object that provides location info
        b = ObservingBlock(target, exposureDuration * u.second, 0,
                           configuration={"object": c.CandidateName, "type": c.CandidateType,
                                          "duration": exposureDuration, "candidate": c},
                           constraints=aggConstraints)  # make the block
        if c.Priority in blocks.keys():  # blocks get grouped by priority level
            blocks[c.Priority].append(b)
        else:
            blocks[c.Priority] = [b]

    # accumulate dictionary of tuples (CandidateName1,CandidateName2)that specifies how long a transition between
    # object1 and object2 should be. these tuples are provided by the configs
    objTransitionDict = {}
    for conf in configDict.values():
        for objNames, val in conf.generateTransitionDict().items():
            objTransitionDict[objNames] = val

    # the transitioner is an object that tells the schedule how long to wait between different combinations of types of blocks
    transitioner = Transitioner(None, {'object': objTransitionDict})

    return blocks, transitioner, candidateDict, configDict

def makeSchedule(candidateDict, configDict, blocks, excludedTimeRanges, startTime, endTime, observer, transitioner, temperature):
    """!
    Do the actual scheduling
    @param observer: the Observer object representing the telescope's location
    @param blacklist: list of designations of targets to ban from being scheduled
    @param whitelist: list of designations of targets to give the highest priority
    @param excludedTimeRanges: list of tuples of times, in integer seconds since epoch, to forbid observations from being scheduled between
    @param temperature: 0-10. represents the randomness applied to scoring; 0 is deterministic
    @return a dataframe representing the schedule, the list of blocks, the schedule object, the dictionary of candidates, and the dictionary of config objects
    """
    tmoScheduler = TMOScheduler(candidateDict, configDict, temperature, constraints=[], observer=observer,
                                transitioner=transitioner,
                                time_resolution=60 * u.second, gap_time=1 * u.minute)
    # create an empty schedule
    schedule = Schedule(Time(startTime), Time(endTime))

    # ----- do the scheduling (modifies schedule inplace) ------------------- ------
    tmoScheduler(blocks, excludedTimeRanges, schedule)

    # convert the schedule to a dataframe and clean it up
    scheduleDf = cleanScheduleDf(schedule.to_table(show_unused=True).to_pandas())
    return scheduleDf, blocks, schedule, candidateDict, configDict


#3. ability to apply a move to a schedule
# should have an atomic structure where a schedule can be represented as an original schedule plus an ordered list of moves
# like linear algebra matrix operations
# should be easy to backtrack to previous schedule by removing a move
# given a schedule, need to be able to generate a list of ALL legal moves

#4. objective function for schedule
# this is just the sum of the score in the start time slot of each observation

#5. creation of tree from a given schedule
# current state of the schedule is a node, schedule+move is a child node for each legal move

#6. monte carlo tree search

