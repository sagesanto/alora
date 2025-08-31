import os
from schedule import *
from scheduler_3 import prepareToSchedule, findCandidates
import pytz
utc = pytz.UTC
from alora.maestro.scheduleLib.genUtils import stringToTime, timeToString
from scheduler import visualizeSchedule

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
candidates, config_dict = findCandidates(OBSERVER, START_TIME.datetime, END_TIME.datetime, BLACKLIST, DB_PATH)
blocks, transitioner, candidateDict, configDict = prepareToSchedule(candidates, config_dict, WHITELIST)
# blocks is {priority: [list of blocks]}
schedule_start_time = START_TIME
schedule_end_time = END_TIME
modularSchedule = ModularSchedule(schedule_start_time, schedule_end_time, 60*u.second)

# setup
observation1 = blocks[3][0]
observation2 = blocks[3][1]
target1 = observation1.target.name
target2 = observation2.target.name
start_time1 = Time(stringToTime(candidateDict[target1].StartObservability))
start_time2 = Time(stringToTime(candidateDict[target2].StartObservability))

# adding test
observation = blocks[3][0]
target = observation.target.name
start_time = Time(stringToTime(candidateDict[target].StartObservability))

add_op = AddObservation(observation, start_time, OBSERVER, transitioner)
add_op.add_to_schedule(modularSchedule)
modularSchedule.visualize("test_adding.png", "test_adding.csv", save=False,show=True)
remove_op = RemoveObservation(observation, start_time, OBSERVER, transitioner)
remove_op.add_to_schedule(modularSchedule)
modularSchedule.visualize("test_removing.png", "test_removing.csv", save=False,show=True)