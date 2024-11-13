# Sage Santomenna 2023

# this is the code for a ModularSchedule, a schedule that is basically a list of Operations that can be applied 
# to a blank schedule. the Operations approach is intented to fit nicely with a monte carlo search that i'm working
# on implementing.
from collections import namedtuple
from astroplan import Observer, FixedTarget, TransitionBlock, Transitioner, ObservingBlock
from astroplan.scheduling import Schedule
from astropy.time import Time
from astropy.coordinates import SkyCoord, EarthLocation
import numpy as np, pandas as pd
from abc import ABC, abstractmethod, ABCMeta, abstractproperty
import unittest
from astropy import units as u
from scheduleLib.genUtils import stringToTime, timeToString, get_sunrise_sunset
import re
import seaborn as sns
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from datetime import datetime
from scheduleLib.sunrise import SunLookup

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

    xMin, xMax = startDt.timestamp(), endDt.timestamp()

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
        dt = datetime.fromtimestamp(value)
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


class ScheduleOperationError(Exception):
    def __init__(self, message):
        super().__init__(message)

# this operation will be applied to a ModularSchedule (subclass of an astroplan Schedule) and will modify it in some way
class Operation(metaclass=ABCMeta):
    @abstractmethod
    def __init__(self, *args,**kwargs):
        pass

    @abstractmethod
    def cancels(self, other_operation):
        """
        return True if this block is canceled by other_operation
        """
        pass

    @abstractmethod
    def add_to_schedule(self, modularSchedule):
        """
        add this block to the provided modularSchedule's operations list
        """
        pass

    @abstractproperty
    def opposite(self):
        """
        return the block that cancels this block
        """
        pass

    def remove_from(self, modularSchedule):
        """
        remove this block from a modularSchedule's operations list
        """
        self.opposite.add_to_schedule(modularSchedule)

    @abstractmethod
    def apply(self, astroplanSchedule):
        """
        apply this operation to a provided Astroplan schedule
        """
        pass

    def __eq__(self, other):
        if not isinstance(other, Operation):
            return False
        return self.__dict__ == other.__dict__


class AddBlock(Operation):
    def __init__(self, block, start_time:Time):
        """
        Operation that will add the given block to a schedule at the given start time
        """
        self.block = block
        self.start_time = start_time
        self.end_time = start_time + block.duration
        self.slot_index = None

    def cancels(self, other_operation):
        if not isinstance(other_operation, RemoveBlock):
            return False
        return self.block == other_operation.block and self.start_time == other_operation.start_time

    def add_to_schedule(self, modularSchedule):
        # add this operation to the modular schedule's operations list
        start_chunk_idx = modularSchedule.index_of(self.start_time)
        end_chunk_idx = modularSchedule.index_of(self.end_time)
        # print(start_chunk_idx,end_chunk_idx)
        if start_chunk_idx is None:
            raise ScheduleOperationError(f"Start time {self.start_time} is not within the schedule")
        if end_chunk_idx is None:
            raise ScheduleOperationError("End time is not within the schedule")
        # check if the block overlaps with any other blocks
        if np.any(modularSchedule.chunk_mask[start_chunk_idx:end_chunk_idx] != -1):
            raise ScheduleOperationError("Block overlaps with another block")
        # now that we know the block is legal, add it to the schedule
        self.slot_index = len(modularSchedule.operations)

        # NOTE: this may cause astroplan issues - should probably reset the block's start time right before computation or smthn
        self.block.start_time = self.start_time
        
        modularSchedule.blocks[self.slot_index] = self.block
        modularSchedule.chunk_mask[start_chunk_idx:end_chunk_idx] = self.slot_index
        # print(modularSchedule.chunk_mask)
        modularSchedule.add_operation(self)
        # print(f"Adding block from {self.start_time} to {self.end_time} ({start_chunk_idx} to {end_chunk_idx}), slot index {self.slot_index})")

        modularSchedule._meta_operations.append(self)

    def apply(self, astroplanSchedule):
        astroplanSchedule.insert_slot(self.start_time, self.block)
    
    @property
    def opposite(self):
        return RemoveBlock(self.block, self.start_time)


class RemoveBlock(Operation):
    def __init__(self, block, start_time:Time):
        """
        this operation removes a block that starts at a given time
        """
        self.block = block
        self.start_time = start_time
        self.end_time = start_time + block.duration
        self.slot_index = None
        self._opposite = None
    
    def cancels(self, other_operation):
        if not isinstance(other_operation, AddBlock):
            return False
        return self.block == other_operation.block and self.start_time == other_operation.start_time
    
    @property
    def opposite(self):
        if self._opposite is None:
            self._opposite = AddBlock(self.block, self.start_time)
        return self._opposite
    
    def add_to_schedule(self, modularSchedule):
        # add this operation to the modular schedule's operations list
        start_chunk_idx = modularSchedule.index_of(self.start_time)
        if start_chunk_idx is None:
            raise ScheduleOperationError("Start time is not within the schedule")
        end_chunk_idx = modularSchedule.index_of(self.end_time)
        if end_chunk_idx is None:
            raise ScheduleOperationError("End time is not within the schedule")
        # check if the block is actually in the schedule
        try:
            if modularSchedule.blocks[modularSchedule.chunk_mask[start_chunk_idx]] != self.block:
                raise ScheduleOperationError("Block is not in the schedule")
        except KeyError as e:
            raise ScheduleOperationError("Block is not in the schedule") from e
        # now that we know the block is legal, add it to the schedule
        self.slot_index = len(modularSchedule.operations)
        modularSchedule.chunk_mask[start_chunk_idx:end_chunk_idx] = -1
        modularSchedule.add_operation(self)

        modularSchedule._meta_operations.append(self)
    
    def apply(self, astroplanSchedule):
        raise ScheduleOperationError("RemoveBlock should never be left un-cancelled in a ModularSchedule")


class SwapBlocks(Operation):
    def __init__(self, block1, block2):
        """
        swap the start times of block1 and block2 (must already be in the schedule)
        """
        self.block1 = block1
        self.block2 = block2
        self.start_1 = self.block1.start_time
        self.start_2 = self.block2.start_time

    
    def cancels(self, other_operation):
        raise NotImplementedError("SwapBlocks creates Remove and Add operations and should never itself end up in the operations list of a ModularSchedule")
    
    def add_to_schedule(self, modularSchedule):
        # we remove the two blocks from the schedule and add them back in with the swapped start times
        remove1 = RemoveBlock(self.block1, self.start_1)
        remove2 = RemoveBlock(self.block2, self.start_2)
        remove1.add_to_schedule(modularSchedule)
        remove2.add_to_schedule(modularSchedule)
        self.block1.start_time = self.start_2
        self.block2.start_time = self.start_1
        add1 = AddBlock(self.block1, self.start_2)
        add2 = AddBlock(self.block2, self.start_1)
        add1.add_to_schedule(modularSchedule)
        add2.add_to_schedule(modularSchedule)

        modularSchedule._meta_operations.append(self)
    
    def apply(self, astroplanSchedule):
        raise NotImplementedError("SwapBlocks should never be directly applied to an astroplan Schedule")
    
    @property
    def opposite(self):
        return SwapBlocks(self.block2, self.block1)

class AddObservation(Operation):
    def __init__(self, observation:ObservingBlock, start_time:Time, observer, transitioner):
        """
        add an observation block and any necessary transition blocks
        """
        self.observation = observation
        self.start_time = start_time
        self.end_time = start_time + observation.duration
        self.observer = observer
        self.transitioner = transitioner
        self.pre_transition = None
        self.post_transition = None
    
    def cancels(self, other_operation):
        raise NotImplementedError

    def add_to_schedule(self, modularSchedule):
        # add up to three AddBlock operations to the schedule's operations list:
        #    one transition, if necessary, before the observation
        #    the observation
        #    one transition, if necessary, after the observation
        previous_block = modularSchedule.previous_block(self.start_time)
        next_block = modularSchedule.next_block(self.start_time)
        if previous_block is not None:
            self.pre_transition = self.transitioner(previous_block, self.observation, self.start_time, self.observer)
            op = AddBlock(self.pre_transition, self.pre_transition.start_time)
            op.add_to_schedule(modularSchedule)

        op = AddBlock(self.observation, self.start_time)
        op.add_to_schedule(modularSchedule)

        if next_block is not None:
            self.post_transition = self.transitioner(self.observation, next_block, next_block.start_time, self.observer)
            op = AddBlock(self.post_transition, self.post_transition.start_time)
            op.add_to_schedule(modularSchedule)

        modularSchedule._meta_operations.append(self)

    def apply(self, astroplanSchedule):
        raise NotImplementedError("AddObservation should never be directly applied to an astroplan Schedule")

    @property
    def opposite(self):
        return RemoveObservation(self.observation, self.start_time, self.observer, self.transitioner)


class RemoveObservation(Operation):
    def __init__(self, observation:ObservingBlock, start_time:Time, observer, transitioner):
        """
        remove an observing block and any transitions associated with it
        """
        self.observation = observation
        self.start_time = start_time
        self.end_time = start_time + observation.duration
        self.observer = observer
        self.transitioner = transitioner
        self.pre_transition = None
        self.post_transition = None
    
    def cancels(self, other_operation):
        raise NotImplementedError
    
    def add_to_schedule(self, modularSchedule):
        # remove up to three AddBlock operations from the schedule's operations list:
        #    one transition, if necessary, before the observation
        #    the observation
        #    one transition, if necessary, after the observation

        # first, check if the observation is actually in the schedule
        start_chunk_idx = modularSchedule.index_of(self.start_time)
        assert modularSchedule.blocks[modularSchedule.chunk_mask[start_chunk_idx]] == self.observation, "Tried to remove an observation that wasn't in the schedule"
        previous_block = modularSchedule.previous_block(self.start_time)
        next_block = modularSchedule.next_block(self.start_time)
        if previous_block is not None:
            if isinstance(previous_block, TransitionBlock):
                self.pre_transition = previous_block
        if next_block is not None:
            if isinstance(next_block, TransitionBlock):
                self.post_transition = next_block
        
        removeObs = RemoveBlock(self.observation, self.start_time)
        removeObs.add_to_schedule(modularSchedule)
        if self.pre_transition is not None:
            removePre = RemoveBlock(self.pre_transition, self.pre_transition.start_time)
            removePre.add_to_schedule(modularSchedule)
        if self.post_transition is not None:
            removePost = RemoveBlock(self.post_transition, self.post_transition.start_time)
            removePost.add_to_schedule(modularSchedule)
        
        modularSchedule._meta_operations.append(self)
        # do we now need to add a transition between the previous block and the next block? would mess up the symmetry of the operations

    @property
    def opposite(self):
        return AddObservation(self.observation, self.start_time, self.observer, self.transitioner)

    def apply(self, astroplanSchedule):
        raise NotImplementedError("RemoveObservation should never be directly applied to an astroplan Schedule")
    

# a ModularSchedule is schedule that is represented as a list of operations that can be applied to a blank schedule.
# when ModularSchedule.compute() is called, the ModularSchedule creates an astroplan Schedule and applies all of its operations to it.
# when an operation is added to the list, it attempts to cancel out any other operations that cancel it out.
class ModularSchedule:
    def __init__(self, start_time: Time, end_time: Time, time_resolution, constraints=None, *args, **kwargs):
        # self.blocks is {slot index: block}
        self.constraints = constraints
        if constraints is None:
            self.constraints = []
        self.blocks = {}
        self.operations = []
        self._meta_operations = []
        self.oldoperations = []
        self.start_time = start_time
        self.end_time = end_time
        self.time_resolution = time_resolution
        self.num_chunks = int(np.ceil((self.end_time-self.start_time).sec/(self.time_resolution.to(u.second).value)))
        # this mask will start filled with -1, but will be filled with the slot index of the observation that is scheduled in that slot:
        self.chunk_mask = np.empty(self.num_chunks)
        self.chunk_mask.fill(-1)
    
    def index_of(self, time):
        if time < self.start_time or time > self.end_time:
            return None
        # floor or ceil?
        return int(np.ceil((time-self.start_time).sec/(self.time_resolution.to(u.second).value)))
    
    def time_of(self, index):
        return self.start_time + index*self.time_resolution

    def previous_block(self, time):
        # return the block that comes before the given time, if there is one
        # loop over chunk_mask, find the first slot that is not -1 and is before the given time
        idx = self.index_of(time)
        if idx is None:
            return None
        for i in range(idx-1, -1, -1):
            if self.chunk_mask[i] != -1:
                return self.blocks[self.chunk_mask[i]]
        return None
    
    def next_block(self, time):
        # return the block that comes after the given time, if there is one
        # loop over chunk_mask, find the first slot that is not -1 and is after the given time
        idx = self.index_of(time)
        if idx is None: return None
        for i in range(idx+1, self.num_chunks):
            if self.chunk_mask[i] != -1:
                return self.blocks[self.chunk_mask[i]]
        return None

    def add_operation(self, operation):
        self.operations.append(operation)
        self.reduce_operations()

    def undo_last_operation(self):
        self.operations.pop()

    def compute(self):
        # apply all operations to the schedule
        sched = Schedule(self.start_time, self.end_time)
        self.reduce_operations()
        for operation in self.operations:
            operation.apply(sched)
        # self.oldoperations.extend(self.operations)
        # self.operations = []
        return sched
    
    def reduce_operations(self):
        # cancel out any operations that cancel each other out
        # for example, if an observation is added and then removed, remove both operations
        for op1 in self.operations:
            for op2 in self.operations:
                if op1.cancels(op2):
                    self.operations.remove(op1)
                    self.operations.remove(op2)
                    break

    def to_df(self):
        """Compute the schedule, then format it as a df"""
        df = self.compute().to_table(show_unused=True).to_pandas()
        df = df.set_axis(
            ['Target', 'Start Time (UTC)', 'End Time (UTC)', 'Duration (Minutes)', 'RA', 'Dec', 'Tags'], axis=1)
        df["Start Time (UTC)"] = df["Start Time (UTC)"].apply(lambda row: row[:-4])
        df["End Time (UTC)"] = df["End Time (UTC)"].apply(lambda row: row[:-4])
        df["Duration (Minutes)"] = df["Duration (Minutes)"].apply(lambda row: round(float(row), 1))
        df["RA"] = df["RA"].apply(lambda row: round(float(row), 4) if row else row)
        df["Dec"] = df["Dec"].apply(lambda row: round(float(row), 4) if row else row)

        return df
        
    def visualize(self,imgpath=None,csvpath=None,save=False,show=True):
        """Compute the schedule, then visualize it"""
        df = self.to_df()
        visualizeSchedule(df, imgpath, csvpath, save=save, show=show)

    def check_constraints(self, candidate_dict, config_dict):
        for constraint in self.constraints:
            if not constraint.check(self, candidate_dict, config_dict):
                raise ScheduleConstraintError(f"Constraint {constraint.name} is not satisfied")


class ScheduleConstraint(ABC):
    @abstractmethod
    def __init__(self, *args, **kwargs):
        pass

    @abstractmethod
    def check(self, modularSchedule, candidate_dict, config_dict, abridged=True):
        pass

    @property 
    @abstractmethod
    def description(self):
        pass

    @property 
    @abstractmethod
    def name(self):
        pass

    def __str__(self):
        return self.name + ": " + self.description


class ScheduleConstraintError(Exception):
    def __init__(self, message):
        super().__init__(message)

# the focus loop constraint requires that each block have an is_focus_loop attribute and a focus_loop_constraint attribute
# the focus_loop_constraint attribute is the maximum amount of time that can elapse between the start of the block and the end of the block
        # this should be infinite if the block has no focus loop constraint
        # this MUST be in units of the schedule's time resolution
class FocusLoopConstraint(ScheduleConstraint):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # what useful information can we precompute that will be valid for the schedule even as it changes?
        self.description = "The focus loop constraint checks if, for each block in the schedule that is not a focus loop, the cumulative duration up to that block is less than or equal to the block's focus loop constraint. It returns True if this condition is met for all blocks, and False otherwise."
        self.name = "Focus Loop Constraint"

    def check(self,modularSchedule, candidate_dict, config_dict,abridged=True):
        duration_arr = np.zeros(len(modularSchedule.blocks))
        constraint_arr = np.zeros(len(modularSchedule.blocks))
        running_diff = 0 # NOTE: we are assuming here that a focus loop was executed immediately before the schedule starts
        time_res_minutes = modularSchedule.time_resolution.to(u.minutes).value
        for i, block in enumerate(modularSchedule.blocks):
            if block.is_focus_loop:
                running_diff = 0
                duration_arr[i] = 0
                constraint_arr[i] = 0
            else:
                config = config_dict[block.target.name]
                focus_loop_constraint = np.ceil(config.maxMinutesWithoutFocus/time_res_minutes)
                running_diff += block.duration
                if abridged and running_diff > focus_loop_constraint:
                    return False, None
                duration_arr[i] = running_diff
                constraint_arr[i] = focus_loop_constraint
        diff = constraint_arr - duration_arr
        return np.all(diff >=0), namedtuple("FocusLoopConstraintReturner", [("duration_arr", duration_arr), ("constraint_arr", constraint_arr), ("diff", diff)])
    
class RepeatObsConstraint(ScheduleConstraint):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.description = "The repeat observations constraint checks that each object is observed the correct number of times. It returns True if this condition is met for all objects, and False otherwise."
        self.name = "Repeat Observations Constraint"

    def check(self, modularSchedule, candidate_dict, config_dict, abridged=True):
        # loop over blocks, count how many times each target is observed
        target_counts = {}
        for block in modularSchedule.blocks:
            if block.target.name not in target_counts:
                target_counts[block.target.name] = 1
            else:
                target_counts[block.target.name] += 1
        # loop over targets, check if the target was observed the correct number of times
        results = {}
        for name, counts in target_counts.items():
            config = config_dict[name]
            if abridged and counts != config.numObs:
                return False, results
            results[name] = counts == config.numObs
        return np.all(list(results.values())), results
    
class ObservabilityConstraint(ScheduleConstraint):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.description = "The observability constraint checks that each observation is scheduled within its observability window. It returns True if this condition is met for all observations, and False otherwise."
        self.name = "Observability Constraint"
    
    def check(self, modularSchedule, candidate_dict, config_dict, abridged=True):
        # loop over blocks, check if the block is scheduled within its observability window
        results = {}
        for block in modularSchedule.blocks:
            candidate = candidate_dict[block.target.name]
            observable = candidate.windowViable(block.start_time.datetime, (block.start_time+block.duration).datetime)
            if abridged and not observable:
                return False, results
            results[block.target.name] = observable
        return np.all(list(results.values())), results

class SunriseSunsetConstraint(ScheduleConstraint):
    # confirm first block is after sunset, last block before sunrise
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def check(self, modularSchedule, candidate_dict, config_dict, abridged=True):
    # first block is the [first non-negative chunk number]th block in the list
        first = modularSchedule.time_of(np.where(modularSchedule.chunk_mask > -1)[0][0])
        last = modularSchedule.time_of(np.where(modularSchedule.chunk_mask > -1)[0][-1])
        sunrise, sunset = get_sunrise_sunset()

# tests
# adding and then removing an observation should result in an empty schedule
# adding and then removing a block should result in an empty schedule
# adding an observation and then adding a block that overlaps with it should result in an error
# removing a block that doesn't exist should result in an error

# unittests
class TestSimple(unittest.TestCase):
    def setUp(self):
        self.block = ObservingBlock(FixedTarget(SkyCoord(0,0,unit="deg")), 600*u.second, 1)
        self.start_time = Time("2020-01-01 00:00:00")
        self.end_time = self.start_time + self.block.duration
        self.add_op = AddBlock(self.block, self.start_time)
        self.remove_op = RemoveBlock(self.block, self.start_time)
        self.schedule_start_time = Time("2020-01-01 00:00:00")
        self.schedule_end_time = Time("2020-01-01 01:00:00")
        self.modularSchedule = ModularSchedule(self.schedule_start_time, self.schedule_end_time, 60*u.second)
    
    def test_cancels(self):
        # test that AddBlock cancels RemoveBlock
        self.assertTrue(self.add_op.cancels(self.remove_op))
    
    def test_equality(self):
        # test that AddBlock is equal to itself
        op2 = AddBlock(self.block, self.start_time)
        self.assertEqual(self.add_op, op2)

    def test_double_opposite(self):
        # test that opposite(opposite(op)) = op
        opposite = self.add_op.opposite
        op2 = opposite.opposite
        self.assertEqual(op2, self.add_op)

    def test_add_to_schedule(self):
        # test that AddBlock adds itself to the schedule
        self.add_op.add_to_schedule(self.modularSchedule)
        self.assertEqual(self.modularSchedule.blocks[0], self.block)
        self.assertEqual(self.modularSchedule.chunk_mask[0], 0)
        self.assertEqual(self.modularSchedule.chunk_mask[10], -1)
        sched = self.modularSchedule.compute()
        self.assertEqual(sched.scheduled_blocks[0], self.block)
    
    def test_apply(self):
        # test that AddBlock adds itself to the astroplan schedule
        sched = Schedule(self.start_time, self.end_time)
        self.add_op.apply(sched)
        self.assertEqual(sched.scheduled_blocks[0], self.block)
    
    def test_opposite(self):
        # test that AddBlock returns the correct opposite
        removeOp = self.add_op.opposite
        self.assertEqual(removeOp.block, self.block)
        self.assertEqual(removeOp.start_time, self.start_time)
        self.assertEqual(removeOp.end_time, self.end_time)
        self.assertEqual(removeOp, self.remove_op)
    
    def test_remove_from(self):
        # test that AddBlock removes itself from the schedule
        self.add_op.add_to_schedule(self.modularSchedule)
        self.add_op.remove_from(self.modularSchedule)
        sched = self.modularSchedule.compute()
        self.assertEqual(sched.observing_blocks, [])
        self.assertTrue(np.all(self.modularSchedule.chunk_mask == -1))

    def test_cant_remove(self):
        # test that RemoveBlock can't be added to the schedule
        with self.assertRaises(ScheduleOperationError):
            self.remove_op.add_to_schedule(self.modularSchedule)
    
    def test_successive_add(self):
        # test that adding two AddBlocks adds both to the schedule
        block2 = ObservingBlock(FixedTarget(SkyCoord(0,0,unit="deg")), 600*u.second, 1)
        start_time2 = Time("2020-01-01 00:10:00")
        end_time2 = start_time2 + block2.duration
        add_op2 = AddBlock(block2, start_time2)
        self.add_op.add_to_schedule(self.modularSchedule)
        add_op2.add_to_schedule(self.modularSchedule)
        sched = self.modularSchedule.compute()
        self.assertEqual(sched.scheduled_blocks[0], self.block)
        self.assertEqual(sched.scheduled_blocks[1], block2)
        self.assertTrue(np.all(self.modularSchedule.chunk_mask[0:10]==0))
        self.assertTrue(np.all(self.modularSchedule.chunk_mask[10:20]==1))
        self.assertTrue(np.all(self.modularSchedule.chunk_mask[20:]==-1))

    def test_add_block_at_schedule_boundaries(self):
        # Test that a block can be added at the start and end times of the schedule
        block_start = ObservingBlock(FixedTarget(SkyCoord(0,0,unit="deg")), 600*u.second, 1)
        block_end = ObservingBlock(FixedTarget(SkyCoord(0,0,unit="deg")), 600*u.second, 1)
        add_op_start = AddBlock(block_start, self.schedule_start_time)
        add_op_end = AddBlock(block_end, self.schedule_end_time - block_end.duration)
        add_op_start.add_to_schedule(self.modularSchedule)
        add_op_end.add_to_schedule(self.modularSchedule)
        sched = self.modularSchedule.compute()
        self.assertEqual(sched.scheduled_blocks[0], block_start)
        self.assertEqual(sched.scheduled_blocks[-1], block_end)

    def test_remove_nonexistent_block(self):
        # Test that trying to remove a block that isn't in the schedule raises an error
        block = ObservingBlock(FixedTarget(SkyCoord(0,0,unit="deg")), 600*u.second, 1)
        remove_op = RemoveBlock(block, self.start_time)
        with self.assertRaises(ScheduleOperationError):
            remove_op.add_to_schedule(self.modularSchedule)

    def test_swap_blocks(self):
        # Test that two blocks can be swapped
        block1 = ObservingBlock(FixedTarget(SkyCoord(0,0,unit="deg")), 600*u.second, 1)
        block2 = ObservingBlock(FixedTarget(SkyCoord(0,0,unit="deg")), 600*u.second, 1)
        add_op1 = AddBlock(block1, self.start_time)
        add_op2 = AddBlock(block2, self.start_time + block1.duration)
        add_op1.add_to_schedule(self.modularSchedule)
        add_op2.add_to_schedule(self.modularSchedule)
        print("\nPre-swap:", self.modularSchedule.chunk_mask)
        block1, block2 = self.modularSchedule.blocks[0], self.modularSchedule.blocks[1]
        swap_op = SwapBlocks(block1, block2)
        swap_op.add_to_schedule(self.modularSchedule)
        print("Post-swap:", self.modularSchedule.chunk_mask)
        sched = self.modularSchedule.compute()
        self.assertEqual(sched.scheduled_blocks[0], block2)
        self.assertEqual(sched.scheduled_blocks[1], block1)


if __name__ == "__main__":
    # run the simple tests
    unittest.main()