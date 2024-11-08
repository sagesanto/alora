import argparse
import os, sys, fileinput, pytz
from datetime import datetime, time, timedelta
from dateutil.relativedelta import relativedelta
import astropy
from astral.sun import sun
from astral import LocationInfo
from astropy.coordinates import EarthLocation
from astropy.time import Time
from astropy import units as u
from astral.sun import sun
from astral.sun import sun
from astral import LocationInfo, zoneinfo
from astral import LocationInfo
from datetime import datetime, timezone, timedelta
from datetime import datetime, timezone, timedelta
from astropy import time, units as u
from astropy import time, units as u
from astropy.coordinates import AltAz, EarthLocation, SkyCoord

from scheduleLib import genUtils

MINUTES_BETWEEN_OBS = 3

TMO = LocationInfo(name='TMO', region='CA, USA', timezone='UTC', latitude=34.36, longitude=-117.63)

HEADER = genUtils.scheduleHeader().split("|")

class Observation:
    # hell on earth, preferred method is fromLine
    def __init__(self, startTime, targetName, RA, Dec, exposureTime, numExposures, duration, filter, ephemTime, dRA,
                 dDec, guiding, description):  # etc
        self.startTime, self.targetName, self.RA, self.Dec, self.exposureTime, self.numExposures, self.duration, self.filter, self.ephemTime, self.dRA, self.dDec, self.guiding, self.description = startTime, targetName, RA, Dec, exposureTime, numExposures, duration, filter, ephemTime, dRA, dDec, guiding, description
        self.endTime = self.startTime + relativedelta(seconds=float(self.duration))
        self.isMPC_NEO = "MPC NEO" in self.description
        if self.isMPC_NEO:
            self.ephemTime = processEphemTime(self.ephemTime,
                                              self.startTime + relativedelta(seconds=float(self.duration) / 2))

    @classmethod
    def fromLine(cls, line):  # this is bad but whatever
#       DateTime|Occupied|Target|Move|RA|Dec|ExposureTime|#Exposure|Filter|Bin2Fits|Guiding|CandidateID|Description
        # need to rework this to split based on keywords, not just on the number of pipes - headers change over time, want to be able to process schedules from any time
        split = line.split('|')
        if len(split) > len(HEADER):
            raise Exception(f"Schedule line ({split}) has too many attributes for its header {HEADER}!")
        description = split.pop()
        # print("Description: ", description)
        split += [None] * (len(HEADER) - 1 - len(split))
        split.append(description)
        d = {HEADER[i]: split[i] for i in range(len(HEADER))}
        startTime = stringToTime(d["DateTime"])
        occupied = d["Occupied"]  # probably always 1
        targetName = d["Target"]
        move = d["Move"]  # probably always 1
        RA = float(d["RA"])
        Dec = float(d["Dec"])
        exposureTime = d["ExposureTime"]
        numExposures = d["#Exposure"]
        duration = float(exposureTime) * float(numExposures)  # seconds
        filter = d["Filter"]
        guiding = d["Guiding"]
        # candidate_ID = split[12]
        descSplit = description.split(" ")
        if "MPC" in description:
            # ephemTime is the time the observation should be centered around
            targetName = targetName[:-2]  # the -2 gets rid of the '_1','_2' etc at end of names.
            ephemTime, dRA, dDec = descSplit[4], descSplit[10], descSplit[12][:-1]  
        else:
            ephemTime = dRA = dDec = None
        return cls(startTime, targetName, RA, Dec, exposureTime, numExposures, duration, filter, ephemTime, dRA,
                    dDec,  guiding, description)

    # this currently is not up to date with the new format of the schedule header - 1/18/24
    # generate a Scheduler.txt line
    def genLine(self, num):  # num is the number (1-index) of times this object has been added to the schedule
        line = timeToString(self.startTime)
        attr = ["1", self.targetName + "_" + str(num), "1", self.RA, self.Dec, self.exposureTime, self.numExposures,
                self.filter, self.description]
        for attribute in attr:
            line = line + "|" + attribute
        return line


# this is an NEO or other target
class Target:
    def __init__(self, name):
        self.name = name
        self.observations = []

    def addObservation(self, obs):
        self.observations.append(obs)
        # add observations here, maybe in dictionary form with useful keyword?


class AutoFocus:
    def __init__(self, desiredStartTime):
        self.startTime = stringToTime(desiredStartTime) if isinstance(desiredStartTime,
                                                                      str) else desiredStartTime
        self.endTime = self.startTime + relativedelta(minutes=5)

    @classmethod
    def fromLine(cls, line):
        time = line.split('|')[0]
        time = stringToTime(time)
        return cls(time)

    # generate a line to put into the scheduler
    def genLine(self):
        return timeToString(self.startTime) + "|1|Focus|0|0|0|0|0|CLEAR|'Refocusing'"


class Schedule:
    def __new__(cls, *args, **kwargs):
        return super(Schedule, cls).__new__(cls)

    def __init__(self, tasks=[],
                 targets={}):  # tasks are AutoFocus or Observation objects, targets is dict of target name to target object
        self.tasks = []
        self.targets = {}

    def appendTask(self, task):
        if isinstance(task, Observation):
            name = task.targetName
            if name not in self.targets.keys():
                self.targets[name] = Target(name)
            self.targets[name].addObservation(task)  # make sure this actually works with scope n stuff
        self.tasks.append(task)

    def appendTasks(self, tasks):
        for task in tasks:
            self.appendTask(task)

    def deleteTask(self, task):
        self.tasks.remove(task)
        if isinstance(task, Observation):
            target = self.targets[task.targetName]
            if task in target.observations:
                target.observations.remove(task)
            if target.observations == []:
                del self.targets[target.name]

    def addAutoFocus(self, desiredTime):
        self.appendTask(AutoFocus(desiredTime))
        # add an autoFocus loop to the schedule

    def toTxt(self):
        lines = "DateTime|Occupied|Target|Move|RA|Dec|ExposureTime|#Exposure|Filter|Description\n\n"
        self.namesDict = {}  # map names of objects to the number of times theyve been observed
        for task in self.tasks:
            if isinstance(task, Observation):
                name = task.targetName
                if name not in self.namesDict.keys():
                    self.namesDict[name] = 1
                else:
                    self.namesDict[name] += 1
                lines += task.genLine(self.namesDict[name]) + "\n"
            else:
                lines += "\n" + task.genLine() + "\n\n"
        print("Enter filename for outputted schedule:", end=" ")
        filename = input()
        with open(filename, "w") as f:
            f.write(lines)
            f.close()
        # add '_1','_2' etc at end of name
        # do the work of converting to usable txt file
        # don't forget to add the template at the top
        # convert time back from time object

    def toDict(self):
        dct = {}
        for task in self.tasks:
            dct[task.startTime] = [task, self.lineNumber(task)]
        return dct

    def lineNumber(self, task):
        return self.tasks.index(task) + 1

    def summarize(self):
        summary = "Schedule with " + str(len(self.targets.keys())) + " targets\n"
        for target in self.targets.values():
            summary = summary + "Target: " + target.name + ", " + str(len(target.observations)) + " observations:\n"
            for obs in target.observations:
                summary = summary + "\t" + timeToString(obs.startTime) + ", " + str(obs.duration) + " second duration\n"
        focusTimes = []
        for task in self.tasks:
            if isinstance(task, AutoFocus):
                focusTimes.append(task.startTime)
        summary += "Schedule has " + str(len(focusTimes)) + " AutoFocus loops:\n"
        for time in focusTimes:
            summary = summary + "\t" + timeToString(time) + "\n"

        return summary

    # probably will want some helper functions


# to maximize the chances that the ephemTime has the correct date on it (if on border between days, UTC), it will assume the month/day/year of the middle of the observation
def processEphemTime(eTime, midTime):
    h = eTime[:2]
    m = eTime[2:-1]
    return midTime.replace(hour=int(h), minute=int(m), second=0)


# convert an angle in decimal, given as a string, to a angle in hour minute second format
def angleToHMS(angle):
    h = float(angle) / 15
    m = 60 * (h - int(h))
    s = 60 * (m - int(m))
    return time(hour=int(h), minute=int(m), second=int(s))


# take time as string from scheduler, return time object
def stringToTime(tstring):  # example input: 2022-12-26T05:25:00.000
    time = datetime.strptime(tstring, '%Y-%m-%dT%H:%M:%S.000')
    return time.replace(tzinfo=pytz.UTC)


def timeToString(time):
    return datetime.strftime(time, '%Y-%m-%dT%H:%M:%S.000')


def friendlyString(time):
    return datetime.strftime(time, '%m/%d %H:%M')


# takes existing schedule file, returns schedule object
def readSchedule(filename):
    lines = []
    tasks = []
    with open(filename, 'r') as f:
        lines = f.readlines()
    cleanedLines = [l.replace("\n", '') for l in lines if l != "\n" and l != " \n"]
    for line in cleanedLines:
        if 'DateTime' in line:  # ignore the template at the top
            continue
        if 'Refocusing' in line:
            tasks.append(AutoFocus.fromLine(line))
        else:  # assume it's an observation
            tasks.append(Observation.fromLine(line))
    schedule = Schedule()
    schedule.appendTasks(tasks)
    return schedule


######### ScheduleChecker  ##########
class Error:
    def __init__(self, eType, lineNum, message, out=None):  # out is a print or other output function
        self.eType, self.lineNum, self.message, self.output = eType, lineNum, message, out

    def out(self):
        if self.output is not None:
            return self.output()
        return "Error encountered in \033[1;33mobservations(s) " + str(
            self.lineNum) + "\033[0;0m with message \"" + self.message + "\""


class Test:
    def __init__(self, name, function):  
        # function returns a status code (0=success, 1=fail, -1=unknown) and an error if necessary
        self.name, self.function = name, function

    def run(self, schedule):  # takes schedule object
        status, error = self.function(schedule)
        return self.name, status, error


def checkSchedule(schedule, testList=None, verbose=True):
    print("Schedule Validation: (Note: line number does not count blank lines)")
    if testList is None:
        testList = tests
    status = []
    errors = 0
    for test in testList:
        status.append(test.run(schedule))
    for state in status:
        if state[1] != 0:
            errors += 1
            if verbose:
                print('\033[1;31m ' + state[0] + ' \033[0;0m', state[2].out())
        elif verbose:
            print('\033[1;32m ' + state[0] + ' \033[0;0m', "No Error!")
    return errors


##### Schedule Tests #####


import sys, warnings
from datetime import time
from astropy.coordinates import Angle
from astropy.utils.exceptions import AstropyWarning

warnings.simplefilter('ignore', category=AstropyWarning)
debug = False  # won't be accurate when this is True, change before using!

# dict of observation durations (seconds) to acceptable offsets (seconds)
obsTimeOffsets = {300: 30, 600: 120, 1200: 300, 1800: 600}


## ----------Error Makers ----------

def noError():
    return Error("No Error", 0, "No Error", lambda: "No Error")


def overlapErrorMaker(task1, task2):
    message = "Observations ending at " + friendlyString(task1[0].endTime) + " and starting at " + friendlyString(
        task2[0].startTime) + " overlap."
    return Error("Time Overlap Error", [task1[1], task2[1]], message)


def sunriseErrorMaker(sunrise, lastTask, timeDiff, lastLineNum):
    message = "Difference between sunrise (" + friendlyString(sunrise) + ") and line #" + str(
        lastLineNum) + " is " + str(timeDiff) + ". Must be at least one hour."
    return Error("Sunrise Error", lastLineNum, message)


def centeringErrorMaker(lineNum, offset, centerTime, correctOffset, midPoint):
    message = "Task on line " + str(lineNum) + " is centered at " + friendlyString(midPoint) + ", which is " + str(
        offset) + " off of its preferred center (" + friendlyString(
        centerTime) + "). Observations of its duration should have an offset of at most " + str(correctOffset) + "."
    return Error("Time-Centering Error", lineNum, message)


def chronoOrderErrorMaker(lineNum):
    message = "Line " + str(lineNum) + " starts after the line that follows it!"
    return Error("Chronological Order Error", lineNum, message)


def autoFocusErrorMaker(lineNum):
    message = "AutoFocus loops are too far apart! Must occur no less than once per hour!"
    return Error("AutoFocus Error", lineNum, message)


def RAdecErrorMaker(lineNum, target_name):
    message = f"({target_name}) RA and Dec not within acceptable limits at time of observation"
    return Error("RA/Dec Error", lineNum, message)


## ----------Tests--------------

def scheduleOverlap(schedule):  # this is all bad
    schedDict = schedule.toDict()
    sortedDict = {key: schedDict[key] for key in
                  sorted(schedDict.keys())}  # this is a lazy and not necessarily performance-friendly way to do this
    keys, vals = list(sortedDict), list(sortedDict.values())
    for i in range(len(vals)):
        if i + 1 <= len(vals) - 1:
            if overlap(vals[i][0], vals[i + 1][0]):
                return 1, overlapErrorMaker(vals[i], vals[i + 1])
    return 0, noError()


def checkSunrise(schedule, loc=TMO):
    global debug
    if debug:
        sunriseUTC = stringToTime("2022-12-26T10:00:00.000")
    else:
        sunriseUTC = genUtils.get_sunrise_sunset()[0]
    end = len(schedule.tasks) - 1
    lastLine = schedule.tasks[end]
    sunriseDiff = sunriseUTC - lastLine.endTime
    if sunriseDiff < timedelta(hours=1):
        return 1, sunriseErrorMaker(sunriseUTC, lastLine, sunriseDiff, end)
    return 0, noError()


def obsCentered(schedule):
    # only call on observations
    for task in schedule.tasks:
        if isinstance(task, Observation) and task.isMPC_NEO:
            centered, offset, maxOffset, midPoint = checkObservationOffset(task)
            lineNum = schedule.lineNumber(task)
            if not centered:
                return 1, centeringErrorMaker(lineNum, offset, task.ephemTime, maxOffset, midPoint)
    return 0, noError()


def chronologicalOrder(schedule):
    for i in range(len(schedule.tasks) - 1):
        if not isBefore(schedule.tasks[i], schedule.tasks[i + 1]):
            return 1, chronoOrderErrorMaker(i)
    return 0, noError()


def autoFocusTiming(schedule):
    prevTime = schedule.tasks[0].startTime
    for task in schedule.tasks:
        if isinstance(task, AutoFocus):
            prevTime = task.startTime
        elif abs(prevTime - task.startTime) > timedelta(hours=1):
            return 1, autoFocusErrorMaker(schedule.lineNumber(task))
    # now check to make sure that the remaining schedule is less that one hour
    # print(prevTime - schedule.tasks[-1].startTime)

    # if abs(prevTime - schedule.tasks[-1].startTime) > timedelta(minutes=65):
    #     return 1, autoFocusErrorMaker(schedule.lineNumber(schedule.tasks[-1]))
    return 0, noError()


def RAdeclimits(schedule):
    for task in schedule.tasks:
        if isinstance(task, Observation):
            if not genUtils.observation_viable(task.startTime, task.RA*u.deg, task.Dec*u.deg):
                print('BAD:',task.RA,task.Dec,task.startTime)
                return 1, RAdecErrorMaker(schedule.lineNumber(task), task.targetName)
    return 0, noError()


# --------Helper Functions---------

# astropy gives us sidereal time as an angle in hours, so we need to convert it to a time
def siderealAngleToTime(angle):
    hours = angle.hour
    return time(hour=int(hours), minute=int((hours - int(hours)) * 60),
                second=int((((hours - int(hours)) * 60) - int((hours - int(hours)) * 60)) * 60))


# check if the RA is within (siderealTime of the observation) + lim1 and (siderealTime of the observation) + lim2
def RAinLimits(observation, lim1, lim2):
    lim1, lim2 = lim1 * u.hourangle, lim2 * u.hourangle
    loc = EarthLocation.from_geodetic('117.63 W', '34.36 N', 100 * u.m)
    startTime = Time(observation.startTime, scale='utc', location=loc)
    endTime = Time(observation.endTime, scale='utc', location=loc)
    startSidereal = startTime.sidereal_time('mean')
    endSidereal = endTime.sidereal_time('mean')
    RA = Angle(observation.RA, unit=u.deg)
    success = RA.is_within_bounds(startSidereal + lim1, endSidereal + lim2)
    if not success and debug:
        print("RA out of bounds!")
        print("RA: ", RA.hms, " Start: ", startSidereal + lim1, " End: ", endSidereal + lim2)
    return success


def decInRange(observation, above, below):
    dec = float(observation.Dec)
    if not (dec > above and dec < below):
        print("Dec failure! Dec: ", dec, dec in range(above, below))
    return dec > above and dec < below


# take in an observation and calculate the difference between the middle of the observation window and the generated "ephemTime" of the object
def offsetFromCenter(observation):
    midPoint = observation.startTime + relativedelta(seconds=float(observation.duration) / 2)
    offset = abs(midPoint - observation.ephemTime)
    return offset, midPoint


# check that an observation is close enough to its intended center
def checkObservationOffset(obs):
    global obsTimeOffsets
    # this will fail if obs.duration is not 300, 600, 1200, or 1800 seconds
    maxOffset = timedelta(seconds=obsTimeOffsets[obs.duration])
    offset, midPoint = offsetFromCenter(obs)
    return offset <= maxOffset, offset, maxOffset, midPoint


# check if task1 starts before task2
def isBefore(task1, task2):
    return task1.startTime < task2.startTime


def overlap(task1, task2):
    start1, end1 = task1.startTime, (
        task1.endTime + timedelta(minutes=MINUTES_BETWEEN_OBS) if isinstance(task1, Observation) else task1.endTime)
    start2, end2 = task2.startTime, (
        task2.endTime + timedelta(minutes=MINUTES_BETWEEN_OBS) if isinstance(task2, Observation) else task2.endTime)
    return (start1 < end2 and end1 > start2) or (start2 < end1 and end2 > start1)  # is this right


# next test: RA/Dec Limits
## -------- Main ----------

# initialize tests
overlapTest = Test("Overlap", scheduleOverlap)
sunriseTest = Test("Done Before Sunrise", checkSunrise)
obsCenteredTest = Test("Observations Centered", obsCentered)
chronOrderTest = Test("Chronological Order", chronologicalOrder)
autoFocusTest = Test("AutoFocus Timing", autoFocusTiming)
RAdecTest = Test("RA/Dec Limits", RAdeclimits)
tests = [overlapTest, sunriseTest, obsCenteredTest, chronOrderTest, autoFocusTest, RAdecTest]


def runTestingSuite(schedule, verbose=True):
    global tests
    return checkSchedule(schedule, tests, verbose)


##### Schedule Scoring #####


from astral.sun import sun
from astral import LocationInfo
from datetime import datetime, timezone, timedelta
from astropy import time, units as u
from astropy.coordinates import AltAz, EarthLocation, SkyCoord
from astropy.time import Time


# schedule = readSchedule("scheduleLib/libFiles/exampleGoodSchedule.txt")


def calculateDowntime(schedule):
    schedDict = schedule.toDict()
    sortedDict = {key: schedDict[key] for key in sorted(schedDict.keys())}
    keys, vals = list(sortedDict), list(sortedDict.values())
    totalDowntime = timedelta()
    downtimes = []
    for i in range(len(vals)):
        if i + 1 <= len(vals) - 1:
            downtime = vals[i + 1][0].startTime - (vals[i][0].endTime + timedelta(minutes=5))
            downtime = downtime if downtime.total_seconds() > 0 else timedelta(minutes=0)
            downtimes.append(downtime)
            totalDowntime += downtime
    return totalDowntime, max(downtimes), totalDowntime / len(downtimes)


def numSchedErrors(schedule):
    return runTestingSuite(schedule, False)


def observationsNearMeridian(schedule):
    numNear = 0
    loc = EarthLocation.from_geodetic('117.63 W', '34.36 N', 100 * u.m)
    for task in schedule.tasks:
        if isinstance(task, Observation):
            obj = SkyCoord(ra=float(task.RA) * u.degree, dec=float(task.Dec) * u.degree, frame='icrs')
            time = Time(task.ephemTime)
            altaz = obj.transform_to(AltAz(obstime=time, location=loc))
            if altaz.alt.degree > 80:
                numNear += 1
    return numNear / len(schedule.tasks)


def countZTobservations(schedule):
    numZTF = 0
    for task in schedule.tasks:
        if isinstance(task, Observation):
            if task.targetName[:2] == "ZT":
                numZTF += 1
    return numZTF


def calculateScore(schedule):
    # dictionary of value names to values
    c = {}

    c["zt"] = countZTobservations(schedule)
    c["errors"] = numSchedErrors(schedule)
    c["downtime"] = calculateDowntime(schedule)[0].total_seconds() / 60
    c["meridian"] = observationsNearMeridian(schedule)
    c["numTargets"] = len(schedule.targets)
    c["numObs"] = len(schedule.tasks)

    score = (c["meridian"]) / (c["errors"] * c["downtime"]) * (
            2 * c["numTargets"] + c["numObs"]) * 80  # this needs tuning
    print("Score:", int(score))


# What makes a good schedule?
#  low downtime
#     lots of objects
#  correct
#  ZTF and SRO objects prioritized
#      near the meridian
#      score each obs, higher score for these is good
#  low airmass (HA close to 0?)

# output
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check the schedule file for correctness.")
    parser.add_argument("scheduleFile", help="Path to the schedule file")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug mode")

    args = parser.parse_args()
    debug = args.debug
    if debug:
        # make schedules
        goodSchedule = readSchedule("libFiles/exampleGoodSchedule.txt")
        # good schedule should pass almost all tests - will fail the autofocus test and the overlap test (doesn't allow 3 minutes between obs)
        badSchedule = readSchedule("libFiles/exampleBadSchedule.txt")
        # bad schedule should fail every test, as so:
        #   - Time Overlap Error: lines 1 and 2 should overlap
        #   - Sunrise Error: last observation happens too close to "sunrise"
        #   - Obs Centered: line 1 is centered off of its target
        #   - Chronological Order: line 5 starts after the line after it
        #   - AutoFocus Timing: line 8 starts more than an hour after the previous autofocus
        #   - RA/Dec Limits: line 15 is outside of the RA/Dec limits
        print("-" * 10)
        print(goodSchedule.summarize())
        checkSchedule(goodSchedule, tests)
        print("-" * 10)
        print(badSchedule.summarize())
        checkSchedule(badSchedule, tests)
        print("-" * 10)
        print("\033[1;31m In debug mode so some inputs simulated! Turn off debug to see accurate results! \033[0;0m")

    else:
        userSchedule = readSchedule(args.scheduleFile)
        checkSchedule(userSchedule, tests)
