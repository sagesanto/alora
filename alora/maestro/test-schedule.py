# Sage Santomenna 2023

import os
from alora.maestro.schedule import *
from alora.maestro.scheduler_3 import prepareToSchedule, findCandidates
import pytz
utc = pytz.UTC
from alora.maestro.scheduleLib.genUtils import stringToTime, timeToString
from alora.maestro.scheduler import visualizeSchedule

print(os.getcwd())
DB_PATH = "files/testing/testing.db"
BLACKLIST = []
LOCATION = EarthLocation.from_geodetic(-117.6815, 34.3819, 0)
OBSERVER = Observer(name='Table Mountain Observatory',
                location=LOCATION,
                timezone=utc,)  # timezone=pytz.timezone('US/Pacific')
WHITELIST = []
START_TIME = Time("2023-12-18 04:30:00")
END_TIME = Time("2023-12-18 13:00:00")

schedule_to_show = None

# we'll read candidates from files/testing/testing.db, which is a frozen real candidateDb 

# if we pass the simple tests from schedule.py, we move on to testing with real candidates
class TestAddBlock(unittest.TestCase):
    def setUp(self):
        self.candidates, self.config_dict = findCandidates(OBSERVER, START_TIME.datetime, END_TIME.datetime, BLACKLIST, DB_PATH)
        self.blocks, self.transitioner, self.candidateDict, self.configDict = prepareToSchedule(self.candidates, self.config_dict, WHITELIST)
        # blocks is {priority: [list of blocks]}
        self.schedule_start_time = START_TIME
        self.schedule_end_time = END_TIME
        self.modularSchedule = ModularSchedule(self.schedule_start_time, self.schedule_end_time, 60*u.second)
    
    
    def test_add_observation(self):
        # Test that an observation can be added to the schedule
        observation = self.blocks[3][0]
        target = observation.target.name
        start_time = Time(stringToTime(self.candidateDict[target].StartObservability))

        add_op = AddObservation(observation, start_time, OBSERVER, self.transitioner)
        add_op.add_to_schedule(self.modularSchedule)
        sched = self.modularSchedule.compute()
        self.assertIn(observation, sched.scheduled_blocks)

    def test_remove_observation(self):
        # Test that an observation can be removed from the schedule
        observation = self.blocks[3][0]
        target = observation.target.name
        start_time = Time(stringToTime(self.candidateDict[target].StartObservability))

        add_op = AddObservation(observation, start_time, OBSERVER, self.transitioner)
        add_op.add_to_schedule(self.modularSchedule)
        remove_op = RemoveObservation(observation, start_time, OBSERVER, self.transitioner)
        remove_op.add_to_schedule(self.modularSchedule)
        sched = self.modularSchedule.compute()
        self.assertNotIn(observation, sched.scheduled_blocks)

    def test_double_add_obs(self):
        # Test that an observation cannot be added twice
        observation = self.blocks[3][0]
        target = observation.target.name
        start_time = Time(stringToTime(self.candidateDict[target].StartObservability))
        add_op = AddObservation(observation, start_time, OBSERVER, self.transitioner)
        add_op.add_to_schedule(self.modularSchedule)
        with self.assertRaises(ScheduleOperationError):
            add_op.add_to_schedule(self.modularSchedule)

    def test_add_two_obs(self):
        global schedule_to_show
        # Test that two observations can be added to the schedule
        observation1 = self.blocks[3][0]
        observation2 = self.blocks[3][1]
        target1 = observation1.target.name
        target2 = observation2.target.name
        start_time1 = Time(stringToTime(self.candidateDict[target1].StartObservability))
        start_time2 = Time(stringToTime(self.candidateDict[target2].StartObservability))

        add_op1 = AddObservation(observation1, start_time1, OBSERVER, self.transitioner)
        add_op1.add_to_schedule(self.modularSchedule)
        add_op2 = AddObservation(observation2, start_time2, OBSERVER, self.transitioner)
        add_op2.add_to_schedule(self.modularSchedule)
        schedule_to_show = self.modularSchedule.compute()
        self.assertIn(observation1, schedule_to_show.scheduled_blocks)
        self.assertIn(observation2, schedule_to_show.scheduled_blocks)

# TODO: I know which targets these are. make the test more specific!!!!!!

if __name__ == "__main__":
    unittest.main()
    df = scheduleToDf(schedule_to_show)
    visualizeSchedule(df,None,None,save=False,show=True)