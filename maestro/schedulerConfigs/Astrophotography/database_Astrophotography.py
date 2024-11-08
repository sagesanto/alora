import configparser
import sys, os, pandas as pd
from datetime import datetime

from astral import LocationInfo
from astropy.time import Time
import pytz

try:
    grandparentDir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir))
    sys.path.append(
        grandparentDir)
    from scheduleLib import genUtils
    from scheduleLib.candidateDatabase import Candidate, CandidateDatabase

    sys.path.remove(grandparentDir)
    genConfig = configparser.ConfigParser()
    genConfig.read(os.path.join(grandparentDir, "files", "configs", "config.txt"))
    aConfig = configparser.ConfigParser()
    aConfig.read(os.path.join(grandparentDir, "files", "configs", "aphot_config.txt"))
except ImportError:
    from scheduleLib import genUtils
    from scheduleLib.candidateDatabase import Candidate, CandidateDatabase

    genConfig = configparser.ConfigParser()
    genConfig.read(os.path.join("files", "configs", "config.txt"))
    aConfig = configparser.ConfigParser()
    aConfig.read(os.path.join("files", "configs", "aphot_config.txt"))

genConfig = genConfig["DEFAULT"]
aConfig = aConfig["DEFAULT"]

ASTROPHOTOGRAPHY_PRIORITY = aConfig.getint("priority")

def evalObservability(candidates, location):
    sunrise, sunset = genUtils.get_sunrise_sunset()
    return [c.evaluateStaticObservability(sunset, sunrise, minHoursVisible=1, locationInfo=location) for c in
            candidates]

def update_database(_db_path):
    location = LocationInfo(name=genConfig["obs_name"], region=genConfig["obs_region"], timezone=genConfig["obs_timezone"],
                            latitude=genConfig.getfloat("obs_lat"),
                            longitude=genConfig.getfloat("obs_lon"))
    synodicStart = datetime.now(tz=pytz.UTC)

    # program:
    # read in candidates populated from catalog by populate_astrophotography.py
    # calculate observabilities, set priorities
    # write to observable.csv file - these can be read later and passed to the scheduler

    # ------- read in candidates as df, transform to candidates
    candidates = Candidate.dfToCandidates(pd.read_csv("schedulerConfigs/Astrophotography/astroRes.csv"))
    # ------- evaluate observability and set priority
    candidates = evalObservability(candidates, location)
    for c in candidates:
        c.Priority = ASTROPHOTOGRAPHY_PRIORITY
        c.ApproachColor = "PURPLE"

    # ------- convert back to df, filter out non-observables
    candidateDf = Candidate.candidatesToDf(candidates)
    if "Rejected Reason" in candidateDf.columns:
        candidateDf = candidateDf.loc[candidateDf["RejectedReason"].isna()].sort_values(by=["Magnitude"],
                                                                                        ascending=True)
    # ------- save to observable.csv, astrophotography's version of a database
    candidateDf.to_csv("schedulerConfigs/Astrophotography/observable.csv", index=None)  # self-locating uncertainty

if __name__ == "__main__":
    update_database(None)