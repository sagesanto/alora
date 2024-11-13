# Sage Santomenna 2023
# program to generate and characterize a schedule. not tested/used in a while, probably needs fixing
import os
import re
import sys
import time
import numpy as np
import matplotlib.pyplot as plt
from collections import Counter

from datetime import datetime

import pandas as pd
import pytz
from astroplan import Observer
from astropy.coordinates import EarthLocation

from scheduler import createSchedule, visualizeSchedule

try:
    sys.path.append(
        os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir)))

    from scheduleLib import genUtils
    from scheduleLib import sCoreCondensed
    from scheduleLib.genUtils import stringToTime, roundToTenMinutes

    sys.path.remove(os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir)))
except:
    from scheduleLib import genUtils
    from scheduleLib import sCoreCondensed
    from scheduleLib.genUtils import stringToTime, roundToTenMinutes

utc = pytz.UTC

if __name__ == "__main__":
    location = EarthLocation.from_geodetic(-117.6815, 34.3819, 0)
    TMO = Observer(name='Table Mountain Observatory',
                   location=location,
                   timezone=utc,
                   )  # timezone=pytz.timezone('US/Pacific')
    blacklist = []
    saveEphems = False
    whitelist = []  # implement this
    excludedTimeRanges = []

    sunriseUTC, sunsetUTC = datetime.strptime("2023-07-30 15:00:00.000", "%Y-%m-%d %H:%M:%S.000"), datetime.strptime(
        "2023-07-30 06:40:00.000", "%Y-%m-%d %H:%M:%S.000")
    sunriseUTC, sunsetUTC = roundToTenMinutes(sunriseUTC), roundToTenMinutes(sunsetUTC)
    savepath = "./scheduleTestingOut"
    candidateDbPath = "./files/20230729_testing_candidateDatabase.db"
    overwrite = False
    numRepeats = 2

    logDf = pd.DataFrame(columns=["Temperature", "Fullness", "Runtime", "RepeatObsSuccess"])
    temperature = 0
    bestSchedRep = None
    bestSchedFull = None
    bestSchedBoth = None
    bestRep = 0
    bestFull = 0
    bestBoth = 0
    for j in range(10):
        times = []
        temperature += 0.1
        print("Starting loop with temperature {}".format(str(temperature)))
        for i in range(numRepeats):
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
                    if sucObs < reqObs:
                        print("{} only got {} out of its {} required observations.".format(desig, str(sucObs), str(reqObs)))
                    reqRepeatObs += reqObs
                    sucRepeatObs += sucObs
            repeatObsSuccess = round(sucRepeatObs / reqRepeatObs, 5) if reqRepeatObs else -1
            logDf.loc[len(logDf.index)] = [temperature, fullness, duration, repeatObsSuccess]
            print(repr(schedule) + ",", str(round(fullness * 100)) + "% full, with {}% repeat obs success.".format(
                str(repeatObsSuccess * 100)))
            if repeatObsSuccess > bestRep:
                bestRep = repeatObsSuccess
                bestSchedRep = (scheduleDf.copy(), repeatObsSuccess, fullness, "bestRepeatSchedule")
            if fullness > bestFull:
                bestFull = fullness
                bestSchedFull = (scheduleDf.copy(), repeatObsSuccess, fullness, "bestFullSchedule")
            if fullness * repeatObsSuccess > bestBoth:
                bestBoth = fullness * repeatObsSuccess
                bestSchedBoth = (scheduleDf.copy(), repeatObsSuccess, fullness, "bestBothSchedule")
        print("Average runtime, {} loops:".format(str(numRepeats)), np.average(times))

    for sched in [bestSchedRep, bestSchedFull, bestSchedBoth]:
        visualizeSchedule(sched[0], os.sep.join([savepath, sched[3] + ".png"]),
                          os.sep.join([savepath, sched[3] + ".csv"]), sunsetUTC, sunriseUTC,
                          addTitleText="{}% full, with {}% repeat obs success.".format(str(round(sched[2] * 100, 3)),
                                                                                       str(sched[1] * 100)), save=True,
                          show=True)

    logDf.to_csv("LogOut.csv")

    plt.scatter(logDf.index, logDf['Fullness'], c=logDf['Temperature'], cmap='viridis', alpha=0.5)
    plt.xlabel('Index#')
    plt.ylabel('Fullness')
    plt.title('Index# vs Fullness (Sized by Temperature)')
    plt.show()

    # Graph 2: index# vs RepeatObsSuccess (sized by temperature)
    plt.scatter(logDf.index, logDf['RepeatObsSuccess'], c=logDf['Temperature'], cmap='viridis', alpha=0.5)
    plt.xlabel('Index#')
    plt.ylabel('RepeatObsSuccess')
    plt.title('Index# vs RepeatObsSuccess (Sized by Temperature)')
    plt.show()

    # Graph 3: temperature vs avg fullness by temperature
    avg_fullness_by_temperature = logDf.groupby('Temperature')['Fullness'].mean()
    plt.plot(avg_fullness_by_temperature.index, avg_fullness_by_temperature.values)
    plt.xlabel('Temperature')
    plt.ylabel('Average Fullness')
    plt.title('Temperature vs Avg Fullness by Temperature')
    plt.show()

    # Graph 4: temperature vs avg RepeatObsSuccess by temperature
    avg_repeatobs_success_by_temperature = logDf.groupby('Temperature')['RepeatObsSuccess'].mean()
    plt.plot(avg_repeatobs_success_by_temperature.index, avg_repeatobs_success_by_temperature.values)
    plt.xlabel('Temperature')
    plt.ylabel('Average RepeatObsSuccess')
    plt.title('Temperature vs Avg RepeatObsSuccess by Temperature')
    plt.show()
