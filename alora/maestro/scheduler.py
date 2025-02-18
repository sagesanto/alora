# Sage Santomenna 2023
from scheduleLib.crash_reports import run_with_crash_writing

def main():

    import configparser
    import os, sys, time, re
    # import timeit
    # from line_profiler_pycharm import profile
    # from pathlib import Path

    # dirname = dirname(PyQt6.__file__)
    # plugin_path = join(Path(__file__).parent, 'PyQt6', 'Qt6', 'plugins')
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
    from astropy.time import Time, TimeDelta
    import matplotlib
    # matplotlib.use('TKAgg')  # very important
    from matplotlib import pyplot as plt
    from matplotlib.colors import ListedColormap

    import scheduleLib.sCoreCondensed
    from scheduleLib.candidateDatabase import Candidate

    # for packaging reasons, i promise

    from os.path import pardir, join, abspath, dirname, isdir
    MODULE_PATH = abspath(join(dirname(__file__)))
    def PATH_TO(fname:str): return join(MODULE_PATH,fname)

    try:
        sys.path.append(MODULE_PATH)

        from scheduleLib import genUtils
        from scheduleLib import sCoreCondensed
        from scheduleLib.genUtils import stringToTime, roundToTenMinutes, configure_logger
        from scheduleLib.module_loader import ModuleManager

        genConfig = genUtils.Config(join(dirname(__file__), "files", "configs", "config.toml"))

    except ImportError:
        from scheduleLib import genUtils
        from scheduleLib import sCoreCondensed
        from scheduleLib.genUtils import stringToTime, roundToTenMinutes, configure_logger
        from scheduleLib.module_loader import ModuleManager

        genConfig = genUtils.Config(join("files", "configs", "config.toml"))

    
    utc = pytz.UTC

    # and the flags are all dead at the tops of their poles

    BLACK = [0, 0, 0]
    RED = [255, 0, 0]
    GREEN = [0, 255, 0]
    BLUE = [0, 0, 255]
    ORANGE = [255, 191, 0]
    PURPLE = [221, 160, 221]

    import logging
    logger = configure_logger("Scheduler")
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    logging.getLogger('matplotlib.font_manager').disabled = True

    focusLoopLenSeconds = genConfig["focus_loop_duration"]


    def generateRandomRow(temperature):
        """!
        Random number generator for temperature and repeat obs stuff
        @return float? this function is probably incorrectly named
        """

        return round(random.uniform(1 - temperature, 1 + temperature), 3)


    class ScorerSwitchboard(astroplan.Scorer):
        def __init__(self, candidateDict, configDict, temperature, *args, **kwargs):
            """!
            A scorer that compiles a score array for the schedule to use.
            """
            self.candidateDict = candidateDict  # desig : candidate
            self.configDict = configDict  # candidate type : config for that type\
            self.temperature = temperature
            super(ScorerSwitchboard, self).__init__(*args, **kwargs)

        def create_score_array(self, time_resolution=1 * u.minute, times=None):
            """!
            Make the score array for all the targets. calls each config's respective function
            @param time_resolution:
            @param times:
            @return
            """
            start = self.schedule.start_time
            end = self.schedule.end_time
            if times is None:
                times = astroplan.time_grid_from_range((start, end), time_resolution)
            scoreArray = np.zeros(shape=(len(self.blocks), len(times)))  # default is zero

            for candType in self.configDict.keys():  # process groups of blocks with the same type
                indices = np.where(np.array([block.configuration["type"] == candType for block in self.blocks]))
                blocksOfType = np.array(self.blocks)[indices]
                if blocksOfType.size == 0:
                    continue
                try:
                    scorer = self.configDict[candType].scorer(self.candidateDict, blocksOfType, self.observer,
                                                            self.schedule,
                                                            global_constraints=self.global_constraints)
                    scoreArr = scorer.create_score_array(time_resolution)
                    modifiedArray = np.array([generateRandomRow(self.temperature) for _ in range(scoreArr.shape[0])])
                    modifiedArray = np.tile(modifiedArray, (scoreArr.shape[1], 1)).T
                    scoreArray[indices] = scoreArr * modifiedArray
                except Exception as e:
                    # raise e
                    # sys.stderr.write("Error when scoring targets of type {}, using generic scorer instead.".format(candType))
                    # sys.stderr.flush()
                    scoreArray[indices] = self.genericScoreArray(blocksOfType, time_resolution) * round(
                        random.uniform(1 - self.temperature, 1 + self.temperature), 3)
            return scoreArray

        def genericScoreArray(self, blocks, time_resolution):
            """!
            Generate a generic array of scores for targets that we couldn't get custom scores for
            """
            start = self.schedule.start_time
            end = self.schedule.end_time
            times = astroplan.time_grid_from_range((start, end), time_resolution)
            scoreArray = np.ones((len(blocks), len(times)))
            for i, block in enumerate(blocks):
                if block.constraints:
                    for constraint in block.constraints:
                        appliedScore = constraint(self.observer, block.target,
                                                times=times)
                        scoreArray[i] *= appliedScore
            for constraint in self.global_constraints:
                scoreArray *= constraint(self.observer, get_skycoord([block.target for block in blocks]), times,
                                        grid_times_targets=True)
            return scoreArray


    # this will need to be written to determine when the last focus was so the schedule knows when its first one needs to be
    def getLastFocusTime(currentTime, schedule):
        """!
        To be implemented: return the time of the most recent focus loop so we know when the next time we have to focus is
        """
        return currentTime


    # @profile
    def makeFocusBlock():
        """!
        Make and return a scheduler block for a focus loop
        """
        dummyTarget = FixedTarget(coord=SkyCoord(ra=0 * u.deg, dec=0 * u.deg), name="Focus")
        return ObservingBlock(dummyTarget, focusLoopLenSeconds * u.second, 0,
                            configuration={"object": "Focus", "type": "Focus",
                                            "duration": focusLoopLenSeconds},
                            constraints=None)


    def plotScores(scoreArray, targetNames, times, title, savepath):
        """!
        Plot the scores of all targets over time
        @param scoreArray: returned from scheduler
        @param targetNames: list of names of targets, in order of rows, for graph labels.
        @param times: list of friendly-formatted strings, corresponding to columns of array, for labeling times
        """
        targetNames = [t for t in targetNames if t != "Focus"]

        x = np.arange(scoreArray.shape[1])  # create x-axis values based on the number of columns
        colors = plt.get_cmap('tab20', len(scoreArray))  # generate a colormap with enough colors

        plt.figure()

        # Plot each row as a line with a different color
        for i in range(len(targetNames)):
            plt.plot(x, scoreArray[i], color=colors(i % 20), label=targetNames[i])

        # Determine a reasonable number of datetime labels to display
        numLabels = min(10, len(times))
        indices = np.linspace(0, len(times) - 1, numLabels, dtype=int)

        # Generate x-axis labels based on sampled times
        xLabels = [times[i] for i in indices]
        plt.xticks(indices, xLabels, rotation=45)

        plt.xlabel('Timestamp')
        plt.ylabel('Score')

        plt.title(title)
        # add a legend with the target names
        plt.legend()

        plt.tight_layout()
        plt.savefig(os.sep.join([savepath, "scorePlot.png"]))


    BLACK = [0, 0, 0]
    RED = [255, 0, 0]
    GREEN = [0, 255, 0]
    BLUE = [0, 0, 255]
    ORANGE = [255, 191, 0]
    PURPLE = [221, 160, 221]


    # @profile
    def visualizeObservability(candidates: list, beginDt, endDt, savepath, title, schedule=None):
        """!
        Visualize the observability windows of candidates as a stacked timeline.

        @param candidates: list of Candidate objects
        @param beginDt: time of beginning of observability window, datetime
        @param endDt: time of end of observability windows, datetime
        @param schedule: WIP: dataframe output by a scheduler. if passed, will be overlaid over the graphics. (not functional)
        @type schedule: DataFrame
        """

        # Filter for candidates with observability windows
        observabilityCandidates = [c for c in candidates if
                                c.hasField("StartObservability") and c.hasField("EndObservability")]

        # Sort candidates by their start times (earliest to latest)
        observabilityCandidates.sort(key=lambda c: genUtils.stringToTime(c.StartObservability))

        # Calculate start and end timestamps
        xMin, xMax = beginDt.timestamp(), endDt.timestamp()
        windowDuration = xMax - xMin

        # Get the unique colors and calculate the number of bars per color
        numCandidates = len(observabilityCandidates)
        numColors = len(plt.cm.tab20.colors)

        # Generate a list of colors using a loop
        colors = []
        for i in range(numCandidates):
            colorIndex = i % numColors
            color = plt.cm.tab20(colorIndex)
            colors.append(color)

        # Set up the plot
        fig, ax = plt.subplots(figsize=(10, 7))
        colorDict = {"GREEN": GREEN, "ORANGE": ORANGE, "RED": RED, "BLACK": BLACK, "PURPLE": PURPLE}

        # if schedule is not None:
        #     df = schedule.to_pandas()
        #     print(df)

        # Iterate over observability candidates and plot their windows
        for i, candidate in enumerate(observabilityCandidates):
            # TODO: take the time to actually figure out why the UTC stuff doesn't work instead of just applying this hardcoded offset:
            startTime = genUtils.stringToTime(candidate.StartObservability)  # UTC conversion. this sucks
            endTime = genUtils.stringToTime(candidate.EndObservability)

            # Convert start time and end time to Unix timestamps
            startUnix = startTime.timestamp()
            endUnix = endTime.timestamp()

            # Calculate the duration of the observability window
            duration = endUnix - startUnix

            # Plot a rectangle representing the observability window
            ax.barh(i, duration, left=startUnix, height=0.6, color=np.array(colorDict[candidate.ApproachColor]) / 255)

            # Place the label at the center of the bar
            ax.text(max(startUnix + duration / 2, xMin + duration / 2), i, candidate.CandidateName, ha='center',
                    va='center', bbox={'facecolor': 'white', 'alpha': 0.75, 'pad': 5})

        # Set the x-axis limits based on start and end timestamps
        ax.set_xlim(xMin, xMax + windowDuration / 10)

        # Format x-axis labels as human-readable datetime
        # @profile
        def formatFunc(value, tickNumber):
            dt = datetime.fromtimestamp(value)
            return dt.strftime("%H:%M\n%d-%b")

        ax.xaxis.set_major_formatter(plt.FuncFormatter(formatFunc))

        # Set the x-axis label
        ax.set_xlabel("Time (UTC)")

        # Set the y-axis label
        ax.set_ylabel("Candidates")

        # Adjust spacing
        plt.subplots_adjust(left=0.1, right=0.95, bottom=0.1, top=0.9)
        plt.suptitle("Candidates for Tonight")
        plt.title(
            beginDt.strftime("%b %d, %Y, %H:%M") + " to " + endDt.strftime(
                "%b %d, %Y, %H:%M"))

        # Show the plot
        plt.savefig(join(savepath, title + ".png"))


    class TMOScheduler(astroplan.scheduling.Scheduler):
        # @profile
        def __init__(self, candidateDict, configDict, temperature, transitioner_dict, *args, **kwargs):
            """!
            Create the scheduler object that will be used to make the schedule
            @param candidateDict: {desig: candidate object} - technically could be constructed from list of blocks, but i think we need it in the function that initializes this object anyway
            @param configDict: {type of candidate (block.configuration["type"]) : TypeConfiguration object}
            @param temperature: float, 0-10. amount of randomness to apply to scoring. 0 = deterministic
            @param transitioner_dict: {object type: Transitioner object}. This will be used for actually doing transitions. the transitioner argument to the parent constructor is not used!
            @param args: normal arguments passed to an astroplan.scheduling.Scheduler constructor
            @param kwargs: normal keyword arguments passed to an astroplan.scheduling.Scheduler constructor
            """

            self.candidateDict = candidateDict
            self.configDict = configDict  #
            self.temperature = temperature
            self.transitioners = transitioner_dict # not to be confused with the transitioner argument to the parent constructor, which is not used!
            super(TMOScheduler, self).__init__(*args, **kwargs)  # initialize rest of schedule with normal arguments

        # @profile
        def __call__(self, blocks: dict, excludedTimeRanges, schedule: Schedule):
            """!
            initiate the schedule-making process
            @param blocks: the dictionary of blocks - for format, see
            @param excludedTimeRanges: list[(tuple(int(startSeconds),int(endSeconds))]
            @param schedule: (presumably empty) schedule to populate
            @return populated schedule
            """

            self.schedule = schedule
            self.schedule.observer = self.observer
            schedule = self._make_schedule(blocks, excludedTimeRanges)
            return schedule

        # @profile
        def _make_schedule(self, allBlocks: dict, excludedTimeRanges):
            """!
            This is the actual function that makes the schedule.
            """

            priorities = list(allBlocks.keys())
            priorities.sort()
            start = self.schedule.start_time
            end = self.schedule.end_time
            timeGrid = astroplan.time_grid_from_range((start, end), self.time_resolution)
            times = [sCoreCondensed.friendlyString(t.datetime) for t in timeGrid]
            schedArr = np.zeros(len(times))  # 0 = slot empty, n = slot full, where n is the priority tier of the object
            for r in excludedTimeRanges:
                iStart, iEnd = max(int((r[0] - start.unix) / self.time_resolution.value), 0), min(
                    int((r[1] - start.unix) / self.time_resolution.value), len(times))
                schedArr[iStart:iEnd] = -1

            # print(schedArr)
            arrayDf = None
            loops = 0
            checks = 0
            scoreSkips = 0
            recordArray = None
            print("Priorities:",priorities)
            for p in priorities:  # go through this loop for each of the targets, in ascending order
                blocks = allBlocks[p]
                # gather all the constraints on each block into a single attribute:
                for b in blocks:
                    if b.constraints is None:
                        b._all_constraints = self.constraints
                    else:
                        b._all_constraints = self.constraints + b.constraints
                    b.observer = self.observer  # set the observer (location and timezone info stuff) (one of the arguments to the constructor that is passed to the parent constructor)

                scorer = ScorerSwitchboard(self.candidateDict, self.configDict, self.temperature, blocks, self.observer,
                                        self.schedule,
                                        global_constraints=self.constraints)  # initialize our scorer object, which will calculate a score for each object at each time slot in the schedule
                scoreArray = scorer.create_score_array(
                    self.time_resolution, times=timeGrid)
                bNames = [b.target.name for b in blocks]

                newScores = pd.DataFrame(scoreArray, columns=times, index=bNames)
                if arrayDf is None:
                    arrayDf = newScores
                else:
                    arrayDf = pd.concat([arrayDf, newScores])
                # print(arrayDf)
                arrayDf.to_csv("arrayDf.csv")

                # this calculates the scores for the blocks at each time, returning a numpy array with dimensions (rows: number of blocks, columns: schedule length/time_resolution (time slots) )
                # if an element in the array is zero, it means the row's corresponding object does not meet all the constraints at the column's corresponding time

                for b in blocks:
                    if self.configDict[b.configuration["type"]].numObs > 1:
                        b.target.name += "_1"
                        b.configuration["object"] += "_1"

                lastFocusTime = getLastFocusTime(start, None)
                # ^ this is a placedholder right now, need to know how long before the beginning of our scheduling period the last SUCCESSFUL focus loop happened
                currentTime = start

                # scheduledDict = {b.target.name.split("_")[0]: b.start_time for b in self.schedule.observing_blocks}
                # scheduledNames = [b.target.name.split("_")[0] for b in self.schedule.observing_blocks]
                scheduledDict = {}
                scheduledNames = []

                while self.schedule.end_time - currentTime > self.time_resolution:
                    loops += 1
                    # print(schedArr)
                    prospectiveDict = {}
                    # print("Trying", len(blocks) - len(scheduledNames), "blocks for time", currentTime)
                    # print("scheduled names:",scheduledNames)
                    # print([b.target.name for b in blocks])
                    # print([b.target.name for b in self.schedule.observing_blocks])
                    currentIdx = int((currentTime - start) / self.time_resolution)
                    # print(currentTime, currentIdx, self.schedule.end_time,self.schedule.end_time-currentTime,type(self.schedule.end_time-currentTime), type(currentTime), type(self.schedule.end_time))
                    if schedArr[currentIdx]:  # higher-priority object already here
                        currentTime += self.gap_time
                        continue
                    bestScore = 0
                    for i, block in enumerate(blocks):
                        durationIdx = int(block.duration / self.time_resolution)
                        if max(scoreArray[i][
                            currentIdx:currentIdx + durationIdx]) < bestScore:  # there's no way this block could get a higher score
                            scoreSkips += 1
                            continue
                        if any(schedArr[
                            currentIdx:currentIdx + durationIdx]) or block in self.schedule.observing_blocks:  # higher-priority object already here or already scheduled this object
                            continue

                        checks += 1
                        config = self.configDict[block.configuration["type"]]
                        focused = False
                        runningTime = currentTime
                        schedQueue = queue.Queue(maxsize=5)
                        # -----------------------------------this is *slow*:--------------------------
                        if (runningTime + block.duration) - lastFocusTime >= timedelta(
                                minutes=config.maxMinutesWithoutFocus):  # focus loop needed
                            focusBlock = makeFocusBlock()  # ----- slow
                            T2 = None
                            if len(self.schedule.slots) != 1:
                                old_block = self.schedule.observing_blocks[-1]
                                old_transitioner = self.transitioners[old_block.configuration["type"]]
                                T2 = old_transitioner(old_block, focusBlock, runningTime,
                                                    self.observer)
                            if T2 is not None:
                                schedQueue.put(T2)
                                runningTime += T2.duration
                            schedQueue.put(focusBlock)
                            runningTime += focusBlock.duration  # ----- slow
                            focused = True
                            if runningTime > self.schedule.end_time:
                                continue
                        else:  # no focus loop needed, but we may need a transition between the last obs and this one
                            T1 = None
                            if len(self.schedule.slots) != 1:
                                old_block = self.schedule.observing_blocks[-1]
                                if old_block.configuration["type"] != "Focus":
                                    transitioner = self.transitioners[old_block.configuration["type"]]
                                else:
                                    transitioner = self.transitioners[block.configuration["type"]]
                                
                                T1 = transitioner(self.schedule.observing_blocks[-1], block, currentTime,
                                                    self.observer)
                                if T1 is not None:  # transition needed
                                    schedQueue.put(T1)
                                    runningTime = T1.end_time
                                if runningTime > self.schedule.end_time:
                                    # print("Not enough time to schedule", block.target.name)
                                    continue
                        # if any score during the block's duration would be 0, if it takes us past the end, or if it intrudes on a previously-scheduled block, reject it
                        # this index calculation takes ~15% of runtime:
                        runningIdx = int((runningTime - start) / self.time_resolution)
                        if any(scoreArray[i][currentIdx:runningIdx + durationIdx] == 0) \
                                or runningTime + block.duration > self.schedule.end_time \
                                or any(schedArr[currentIdx:runningIdx + durationIdx]):
                            continue
                        if re.sub('_\\d', '', block.target.name) in scheduledDict.keys():
                            if config.minMinutesBetweenObs:
                                if runningTime - scheduledDict[re.sub('_\\d', '', block.target.name)] < timedelta(
                                        minutes=config.minMinutesBetweenObs):
                                    continue
                        schedQueue.put(block)
                        score = scoreArray[i, runningIdx]
                        bestScore = bestScore if bestScore > score else score
                        # prospectiveDict[score * 0.8 if focused else score] = schedQueue
                        prospectiveDict[score] = schedQueue

                    if not len(prospectiveDict):
                        currentTime += self.gap_time
                        # print("No blocks found for", currentTime)
                        continue

                    maxIdx = max(prospectiveDict.keys())
                    bestQueue = prospectiveDict[maxIdx]
                    for i in range(bestQueue.qsize()):
                        b = bestQueue.get()
                        if isinstance(b, ObservingBlock):
                            if b.target.name == "Focus":
                                lastFocusTime = currentTime
                            else:
                                scheduledDict[re.sub('_\\d', '', b.target.name)] = currentTime
                                scheduledNames.append(re.sub('_\\d', '', b.target.name))
                                # print("Scheduled names:",scheduledNames)
                                justInserted = b
                        # print("Inserting",b)
                        self.schedule.insert_slot(currentTime, b)
                        currentTime += b.duration
                    # block off the schedule where we just added something:
                    schedArr[currentIdx:int((currentTime - start) / self.time_resolution)] = p  
                    # 'currentIdx' is still the idx from the beginning of this pass
                    config = self.configDict[justInserted.configuration["type"]]
                    numPrev = len(
                        [i for j, i in enumerate(scheduledNames) if i == re.sub('_\\d', '', justInserted.target.name)])
                    if numPrev < config.numObs:
                        justIdx = blocks.index(justInserted)  # very efficient lol
                        c = self.candidateDict[re.sub('_\\d', '', justInserted.target.name)]
                        conf = self.configDict[c.CandidateType]
                        newArr = copy.copy(scoreArray[justIdx, :])
                        newArr = conf.scoreRepeatObs(c, newArr, numPrev, currentTime)
                        scoreArray = np.r_[scoreArray, [newArr]]

                        # --------- this copy might be slow:
                        blockCopy = copy.deepcopy(justInserted)
                        blockCopy.target.name = blockCopy.target.name[:-2] + "_" + str(numPrev + 1)
                        blockCopy.configuration["object"] = blockCopy.target.name[:-2] + "_" + str(numPrev + 1)
                        blocks.append(blockCopy)

                    continue

                recordArray = np.r_[recordArray, scoreArray] if recordArray is not None else scoreArray
            # print("Loops:", loops)
            # print("Checks:", checks)
            # print("Skips:", scoreSkips)
            allBlocksList = []
            for l in allBlocks.values():
                allBlocksList.extend(l)
            # NOTE: this function call only "works" because the Astrophotography targets come last in the array - that's why we can cut them from the list
            non_aphot_blocks = [b.target.name for b in allBlocksList if b.configuration["type"] != "Astrophotography"]
            if len(non_aphot_blocks):
                plotScores(recordArray, non_aphot_blocks, times, "All Targets", savepath)
            return self.schedule


    # @profile
    def visualizeSchedule(scheduleDf: pd.DataFrame, plotSavepath, csvSavepath, startDt=None, endDt=None, addTitleText=None,
                        save=True, show=False):
        """!
        Take a schedule dataframe and visualize it. optionally, save the schedule csv
        @param scheduleDf: the schedule dataframe, cleaned
        @param plotSavepath: where to save the generated plot
        @param csvSavepath: where to save the schedule csv file
        @param addTitleText: optional additional title text
        @param save: bool. whether or not to save the image and csv
        @param show: bool. whether or not to show the image when generated, pausing the program the plot is closed
        @return None
        """

        schedule = scheduleDf.loc[(scheduleDf["Target"] != "TransitionBlock")]
        if startDt is None:
            startDt = stringToTime(schedule.iloc[0]["Start Time (UTC)"])
        if endDt is None:
            endDt = stringToTime(schedule.iloc[len(schedule.index) - 1]["End Time (UTC)"])

        print("Start:", startDt, "End:", endDt)
        print("Start tz:", startDt.tzinfo, "End tz:", endDt.tzinfo)
        xMin, xMax = startDt.timestamp(), endDt.timestamp()
        print("Min:", xMin, "Max:", xMax)

        xTicks = []
        val = xMax - xMax % 3600
        while val > xMin:
            xTicks.append(val)
            val -= 3600

        targetNames = schedule.loc[(schedule["Target"] != "Unused Time") & (schedule["Target"] != "TransitionBlock")][
            "Target"].tolist()
        targetNames = list(set([re.sub('_\\d', '', t) for t in targetNames]))
        numTargets = len(targetNames)

        sbPalette = sns.color_palette("hls", numTargets)
        cmap = ListedColormap(sns.color_palette(sbPalette).as_hex())

        colorDict = {}
        for i in range(numTargets):
            color = cmap(i)
            colorDict[targetNames[i]] = color
        colorDict["Unused Time"] = plt.cm.tab20(14)
        colorDict["TransitionBlock"] = plt.cm.tab20(17)

        fig, ax = plt.subplots(figsize=(4, 8))
        for i in range(0, len(schedule.index)):
            row = schedule.iloc[i]
            startTime, endTime = stringToTime(row["Start Time (UTC)"]), stringToTime(row["End Time (UTC)"])
            startTime, endTime = startTime.replace(tzinfo=pytz.utc), endTime.replace(tzinfo=pytz.utc)
            name = row["Target"]

            startUnix = startTime.timestamp()
            endUnix = endTime.timestamp()

            duration = endUnix - startUnix

            ax.bar(0, duration, bottom=startUnix, width=0.6, color=colorDict[re.sub('_\\d', '', name)],
                edgecolor="black")

            if name != "Unused Time" and name != "Focus":
                ax.text(0, max(startUnix + duration / 2, xMin + duration / 2), name, ha='center',
                        va='center' if name != "Focus" else "top", bbox={'facecolor': 'white', 'alpha': 0.75,
                                                                        'pad': 3})

        ax.set_ylim(xMin, xMax)

        # @profile
        def formatFunc(value, tickNumber):
            dt = datetime.fromtimestamp(value, tz=pytz.utc)
            return dt.strftime("%H:%M\n%d-%b")

        ax.yaxis.set_major_formatter(plt.FuncFormatter(formatFunc))
        ax.set_yticks(xTicks)
        # ax.set_ylabel("Time (UTC)")

        ax.set_xticks([])
        ax.invert_yaxis()
        plt.subplots_adjust(left=0.15, right=0.85, bottom=0.05, top=0.9)
        title = startDt.strftime("%H:%M") + " to " + endDt.strftime(
            "%H:%M") + " UTC\n"
        if addTitleText:
            title += addTitleText
        plt.suptitle("Schedule for " + startDt.strftime("%b %d, %Y"))
        plt.title(title)

        if save:
            plt.savefig(plotSavepath)
            schedule.to_csv(csvSavepath, index=None)

        if show:
            plt.show()
            plt.close()


    # @profile

    def cleanScheduleDf(df: pd.DataFrame):
        """!
        Clean and format a schedule dataframe
        @param df: schedule dataframe, as prepared by createSchedule
        """
        df = df.set_axis(
            ['Target', 'Start Time (UTC)', 'End Time (UTC)', 'Duration (Minutes)', 'RA', 'Dec', 'Tags'], axis=1)
        df["Start Time (UTC)"] = df["Start Time (UTC)"].apply(lambda row: row[:-4])
        df["End Time (UTC)"] = df["End Time (UTC)"].apply(lambda row: row[:-4])
        df["Duration (Minutes)"] = df["Duration (Minutes)"].apply(lambda row: round(float(row), 1))
        df["RA"] = df["RA"].apply(lambda row: round(float(row), 4) if row else row)
        df["Dec"] = df["Dec"].apply(lambda row: round(float(row), 4) if row else row)

        return df


    # @profile
    def createSchedule(observer: Observer, startTime: datetime, endTime: datetime, blacklist, whitelist, excludedTimeRanges,
                    candidateDbPath: str, temperature=0):
        """!
        Do the actual scheduling
        @param observer: the Observer object representing the telescope's location
        @param blacklist: list of designations of targets to ban from being scheduled
        @param whitelist: list of designations of targets to give the highest priority
        @param excludedTimeRanges: list of tuples of times, in integer seconds since epoch, to forbid observations from being scheduled between
        @param temperature: 0-10. represents the randomness applied to scoring; 0 is deterministic
        @return a dataframe representing the schedule, the list of blocks, the schedule object, the dictionary of candidates, and the dictionary of config objects
        """

        configDict = {}

        modules = ModuleManager().load_active_modules()
        for k, mod in modules.items():
            typeName, conf = mod.getConfig(observer)  # modules must have this function
            configDict[typeName] = conf 
        
        # import configurations from python files placed in the schedulerConfigs folder

        # root = "schedulerConfigs"
        # root_directory = PATH_TO("schedulerConfigs")
        # module_names = []
        # for dir in [f"{root}."+d for d in os.listdir(root_directory) if isdir(join(root_directory, d))]:
        #     module_names.append(dir)
        # for m in module_names:
        #     try:
        #         module = import_module(m, "schedulerConfigs")
        #         typeName, conf = module.getConfig(observer)  # modules must have this function
        #         configDict[typeName] = conf
        #     except Exception as e:
        #         logger.error(f"Can't import config module {m}: {e}. Fix and try again.")
        #         raise e

        # turn the lists of candidates into one list
        candidates = [candidate for candidateList in [c.selectCandidates(startTime, endTime, candidateDbPath) for c in configDict.values()]
                        for candidate in candidateList if candidate.CandidateName not in blacklist]

        if len(candidates) == 0:
            logger.warning("No candidates provided - nothing to schedule. Exiting.")
            sys.stdout.flush()
            exit(0)

        # blocks are what will be slotted into the schedule - blocks specify a target but not a set start or end time
        blocks = {}  # blocks by priority
        for i, c in enumerate(candidates):
            c.Priority = c.Priority + 1 if c.CandidateName not in whitelist else 1  # ---- manage the whitelist -----
            if c.Priority not in blocks.keys():
                blocks[c.Priority] = []
            # c.RA = genUtils.ensureAngle(str(c.RA) + "h")
            # c.Dec = genUtils.ensureAngle(float(c.Dec))

        designations = [candidate.CandidateName for candidate in candidates]
        print("Considering the following targets for scheduling:", designations)
        candidateDict = dict(zip(designations, candidates))

        # WARNING - this can prevent any observations of targets whose observability duration = NumExposures * ExposureTime
        # constraint on when the observation can *start*
        # timeConstraintDict = {c.CandidateName: TimeConstraint(Time(stringToTime(c.StartObservability)),
        #                                                     Time(stringToTime(c.EndObservability) - timedelta(
        #                                                         seconds=float(c.NumExposures) * float(c.ExposureTime))))
        #                     for c in candidates}
        timeConstraintDict = {c.CandidateName: TimeConstraint(Time(c.StartObservability),
                                                            Time(c.EndObservability))
                            for c in candidates}

        # make a dict of constraints to put on all targets of a given type (specified optionally by config py file)
        typeSpecificConstraints = {}
        for typeName, conf in configDict.items():
            typeSpecificConstraints[
                typeName] = conf.generateTypeConstraints()  # dictionary of {type of target: list of astroplan constraints, initialized}

        # --- create the blocks ---
        blocks = {}  # dictionary that stores targets grouped by priority level
        for c in candidates:
            exposureDuration = c.NumExposures * c.ExposureTime.to_value("second")  # calculate block duration
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

        # make transitioner objects that tell the schedule how to transition between different types of blocks
        transitioners = {} # {configName: Transitioner}
        for confname, conf in configDict.items():
            transitioners[confname] = Transitioner(None, {'object': conf.generateTransitionDict()})
        
        dummy_transitioner = Transitioner(None, {'object': {"default": None}})
        # the transitioner is an object that tells the schedule how long to wait between different combinations of types of blocks

        # the scheduler is the object that is used to make the schedule
        tmoScheduler = TMOScheduler(candidateDict, configDict, temperature, transitioner_dict=transitioners, constraints=[], observer=observer,
                                    transitioner=dummy_transitioner,
                                    time_resolution=60 * u.second, gap_time=1 * u.minute)
        # create an empty schedule
        schedule = Schedule(Time(startTime), Time(endTime))

        # ----- do the scheduling (modifies schedule inplace) ------------------- ------
        tmoScheduler(blocks, excludedTimeRanges, schedule)

        # convert the schedule to a dataframe and clean it up
        scheduleDf = cleanScheduleDf(schedule.to_table(show_unused=True).to_pandas())
        return scheduleDf, blocks, schedule, candidateDict, configDict


    # @profile
    def lineConverter(row: pd.Series, configDict, candidateDict, runningList: list, spath):
        """!
        Using each line of the raw schedule dataframe, ask each config to generate schedule lines for its targets
        @param configDict:
        @param candidateDict:
        @param runningList: list of strings that will be written to text file. persistent
        @param spath: the path of the schedule output dir. will be used to output ephems
        @return None
        """
        targetName = row.iloc[0]

        if targetName in ["Unused Time", "TransitionBlock"]:
            return
        # runningList.append("\n")
        if targetName == "Focus":
            targetStart = stringToTime(row.iloc[1])
            runningList.append(genUtils.AutoFocus(targetStart).genLine())
            runningList.append("\n")
            return

        lineOrLines = configDict[row["Tags"]["type"]].generateSchedulerLine(row, targetName, candidateDict, spath)
        if isinstance(lineOrLines, str):
            runningList.append(lineOrLines)
        else:
            runningList.extend(lineOrLines)
            # raise ValueError("Object " + str(targetName) + " doesn't have a schedule line generator. " + str(row))


    # @profile
    def scheduleToTextFile(scheduleDf, configDict, candidateDict, prevSched=None, spath=None):
        """!
        Format a schedule to be text-file friendly
        """
        # each target type will need to have the machinery to turn an entry from the scheduleDf + the candidateDict into a
        # scheduler line - maybe we'll make a default version later
        linesList = [genUtils.scheduleHeader()+"\n\n"]
        scheduleDf.apply(lambda row: lineConverter(row, configDict, candidateDict, linesList, spath), axis=1)
        # print(linesList)
        linesList = [l+"\n" if not l.endswith("\n") else l for l in linesList]
        return linesList


    def retrieveExcludeList(lsStr):
        """!
        Take a convoluted string we pass in from Maestro and make it a list of tuples of ints
        @param lsStr:
        @return
        """
        if lsStr == '':
            return []
        ls = lsStr.split(',')
        return [(int(i[0]), int(i[1])) for i in [a.split("/") for a in ls]]


    def toList(lsStr, dType=str):
        """!
        Turn a comma separated string into a list of objects of type dType
        """
        return [dType(i) for i in lsStr.split(",")]

    location = EarthLocation.from_geodetic(-117.6815, 34.3819, 0)
    TMO = Observer(name='Table Mountain Observatory',
                location=location,
                timezone=utc,
                )  # timezone=pytz.timezone('US/Pacific')
    blacklist = []
    saveEphems = False
    whitelist = []  # implement this
    excludedTimeRanges = []
    temperature = 0.1
    numRuns = 1

    # set params
    if len(sys.argv) == 1:
        sunriseUTC, sunsetUTC = genUtils.get_sunrise_sunset()
        sunriseUTC, sunsetUTC = roundToTenMinutes(sunriseUTC), roundToTenMinutes(sunsetUTC)
        sunriseUTC -= timedelta(hours=1)  # to account for us closing the dome one hour before sunrise
        sunsetUTC = max(sunsetUTC, pytz.UTC.localize(datetime.utcnow()))
        savepath = PATH_TO("/files/outputs/scheduleOut")
        candidateDbPath = genUtils.get_candidate_database_path()
        overwrite = False
    else:
        settings = json.loads(sys.argv[1])
        localtz = datetime.now().astimezone().tzinfo
        sunsetUTC = datetime.fromtimestamp(settings["scheduleStartTimeSecs"], tz=localtz).astimezone(pytz.utc)
        sunriseUTC = datetime.fromtimestamp(settings["scheduleEndTimeSecs"], tz=localtz).astimezone(pytz.utc)
        print(f"Making schedule from {sunsetUTC} to {sunriseUTC}")
        savepath = settings["scheduleSaveDir"]
        blacklist = toList(sys.argv[2])
        whitelist = toList(sys.argv[3])
        excludedTimeRanges = retrieveExcludeList(sys.argv[4])
        # for r in excludedTimeRanges:
        numRuns = settings["schedulerRuns"]
        temperature = settings["temperature"] / 10
        print(temperature)
        print(f"Making schedule from {sunsetUTC} to {sunriseUTC}") 
        candidateDbPath = settings["candidateDbPath"]
        saveEphems = settings["schedulerSaveEphems"]
        overwrite = True

    # prepare saveloc
    if not os.path.exists(savepath):
        os.mkdir(savepath)
    elif overwrite:  # safety precaution lol
        for out in ["schedule.txt", "schedule.csv", "schedule.png", "scorePlot.png", "visibilityAll.png"]:
            try:
                os.remove(join(savepath, out))
            except:
                pass
        try:
            shutil.rmtree(join(savepath,"ephems"), ignore_errors=True)
            os.mkdir(join(savepath,"ephems"))
        except:
            pass

    logDf = pd.DataFrame(columns=["Temperature", "Fullness", "Runtime", "RepeatObsSuccess"])
    bestSchedRep = None
    bestSchedFull = None
    bestSchedBoth = None
    bestRep = 0
    bestFull = 0
    bestBoth = 0
    times = []

    ephemSpath = None
    if saveEphems:
        ephemSpath = join(savepath, "ephems")
        try:
            os.mkdir(ephemSpath)
        except:
            pass

    # make schedule(s)
    for i in range(numRuns):
        start = time.time()
        scheduleDf, blocks, schedule, candidateDict, configDict = createSchedule(TMO, sunsetUTC, sunriseUTC,
                                                                                blacklist, whitelist,
                                                                                excludedTimeRanges,
                                                                                candidateDbPath,
                                                                                temperature=temperature)
        duration = time.time() - start
        times.append(duration)
        unused = scheduleDf.loc[scheduleDf["Target"] == "Unused Time"]["Duration (Minutes)"].sum()
        total = scheduleDf["Duration (Minutes)"].sum()
        fullness = round(1 - (unused / total), 3)
        usedDesigsR = [re.sub('_\\d', '', t) for t in scheduleDf["Target"].tolist() if
                    t != "Unused Time" and t != "Focus" and t != "TransitionBlock"]
        counts = Counter(usedDesigsR)
        reqRepeatObs = 0
        sucRepeatObs = 0
        for desig in list(counts):
            reqObs = configDict[candidateDict[desig].CandidateType].numObs
            if reqObs > 1:
                sucObs = counts[desig]
                # if sucObs < reqObs:
                #     print("{} only got {} out of its {} required observations.".format(desig, str(sucObs), str(reqObs)))
                reqRepeatObs += reqObs
                sucRepeatObs += sucObs
        repeatObsSuccess = round(sucRepeatObs / reqRepeatObs, 5) if reqRepeatObs else 1
        logDf.loc[len(logDf.index)] = [temperature, fullness, duration, repeatObsSuccess]
        print(repr(schedule) + ",", str(round(fullness * 100)) + "% full, with {}% repeat obs success.".format(
            str(repeatObsSuccess * 100)))
        if repeatObsSuccess >= bestRep:
            bestRep = repeatObsSuccess
            bestSchedRep = (scheduleDf.copy(), repeatObsSuccess, fullness, "bestRepeatSchedule")
        if fullness >= bestFull:
            bestFull = fullness
            bestSchedFull = (scheduleDf.copy(), repeatObsSuccess, fullness, "bestFullSchedule")
        if fullness * repeatObsSuccess >= bestBoth:
            bestBoth = fullness * repeatObsSuccess
            bestSchedBoth = (scheduleDf.copy(), repeatObsSuccess, fullness, "bestBothSchedule")

    if numRuns > 1:
        for sched, name in [(bestSchedFull, "BestFullness"),
                            (bestSchedBoth, "BestCombined"), (bestSchedRep, "BestRepeatSuccess")]:
            visualizeSchedule(sched[0], join(savepath, f"{sched[3]}.png"),
                            join(savepath, f"{sched[3]}.csv"), sunsetUTC, sunriseUTC,
                            addTitleText="{}% full, with {}% repeat obs success.".format(
                                str(round(sched[2] * 100, 3)),
                                str(sched[1] * 100)), save=True,
                            show=False)
            schedLines = scheduleToTextFile(sched[0], configDict, candidateDict, spath=ephemSpath)
            with open(join(savepath, f'{name}.txt'), "w") as f:
                f.writelines(schedLines)
        usedDesigs = []
        for d in usedDesigsR:  # filter for unique candidate names after chopping off the _1/_2 etc. this used to be done with a set but that didn't preserve order
            if d not in usedDesigs:
                usedDesigs.append(d)
        candidatesInSchedule = [candidateDict[d] for d in usedDesigs]

        # do the observing log
        if candidatesInSchedule:
            try:
                df = Candidate.candidatesToDf(candidatesInSchedule)
                df = genUtils.prettyFormat(df)
                df.to_csv(join(savepath,"observingLog.csv"), index=False)
                visualizeObservability(candidatesInSchedule, sunsetUTC, sunriseUTC, savepath, "visibilityAll")
            except Exception as e:
                sys.stderr.write("Writing obs log failed with exception " + repr(e))

        logDf.to_csv(join(savepath,"LogOut.csv"))

    print(repr(schedule) + ",", str(round(fullness * 100)) + "% full")
    usedDesigs = []
    usedDesigsR = [re.sub('_\\d', '', t) for t in scheduleDf["Target"].tolist() if
                t != "Unused Time" and t != "Focus" and t != "TransitionBlock"]
    for d in usedDesigsR:  # filter for unique candidate names after chopping off the _1/_2 etc. this used to be done with a set but that didn't preserve order
        if d not in usedDesigs:
            usedDesigs.append(d)
    candidatesInSchedule = [candidateDict[d] for d in usedDesigs]

    # do the observing log
    if candidatesInSchedule:
        try:
            df = Candidate.candidatesToDf(candidatesInSchedule)
            df = genUtils.prettyFormat(df)
            df.to_csv(join(savepath,"observingLog.csv"), index=False)
            visualizeObservability(candidatesInSchedule, sunsetUTC, sunriseUTC, savepath, "visibilityAll")
        except Exception as e:
            sys.stderr.write("Writing obs log failed with exception " + repr(e))

    # schedule png
    visualizeSchedule(scheduleDf, join(savepath, "schedule.png"), join(savepath, "schedule.csv"),
                    sunsetUTC, sunriseUTC)

    logger.info("Status:Schedule visualized.")

    schedLines = scheduleToTextFile(scheduleDf, configDict, candidateDict, spath=ephemSpath)
    sched_outpath = join(savepath, "schedule.txt")
    with open(sched_outpath, "w") as f:
        f.writelines(schedLines)
    print(f"Wrote schedule to {sched_outpath}")
    try:
        checkerSched = scheduleLib.sCoreCondensed.readSchedule(join(savepath, "schedule.txt"))
        scheduleLib.sCoreCondensed.checkSchedule(checkerSched)
    except Exception as e:
        sys.stderr.write("Got error trying to check schedule: " + repr(e) + "\n")
        raise

if __name__ == "__main__":
    run_with_crash_writing("scheduler",main)