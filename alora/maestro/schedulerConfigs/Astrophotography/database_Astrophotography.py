import configparser
import sys, os, pandas as pd
from datetime import datetime
from os.path import join, dirname, pardir, abspath

from astral import LocationInfo
from astropy.time import Time
import pytz

from os.path import pardir, join, abspath, dirname

from alora.config import observatory_location

MODULE_PATH = abspath(join(dirname(__file__), pardir, pardir))
def PATH_TO(fname:str): return join(MODULE_PATH,fname)

try:
    sys.path.append(MODULE_PATH)
    from scheduleLib import genUtils
    from scheduleLib.candidateDatabase import Candidate, CandidateDatabase

    # sys.path.remove(grandparentDir)
    genConfig = genUtils.Config(join(MODULE_PATH, "files", "configs", "config.toml"))
    aConfig = genUtils.Config(join(dirname(__file__), "config.toml"))

except ImportError:
    from scheduleLib import genUtils
    from scheduleLib.candidateDatabase import Candidate, CandidateDatabase

    genConfig = genUtils.Config(join("files", "configs", "config.toml"))
    aConfig = genUtils.Config(join(dirname(__file__), "config.toml"))

ASTROPHOTOGRAPHY_PRIORITY = aConfig["priority"]

def evalObservability(candidates: list[Candidate], location):
    sunrise, sunset = genUtils.get_sunrise_sunset()
    return [c.evaluateStaticObservability(sunset, sunrise, minHoursVisible=1, locationInfo=location) for c in
            candidates]

def update_database(_db_path):
    location = observatory_location
    synodicStart = datetime.now(tz=pytz.UTC)

    # program:
    # read in candidates populated from catalog by populate_astrophotography.py
    # calculate observabilities, set priorities
    # write to observable.csv file - these can be read later and passed to the scheduler

    # ------- read in candidates as df, transform to candidates
    candidates = Candidate.dfToCandidates(pd.read_csv(PATH_TO(join("schedulerConfigs","Astrophotography","astroRes.csv"))))
    # ------- evaluate observability and set priority
    candidates = evalObservability(candidates, location)
    for c in candidates:
        c.Priority = ASTROPHOTOGRAPHY_PRIORITY
        c.ApproachColor = "PURPLE"

    print(type(candidates[0]))
    print(candidates[0])
    print("candidate:", candidates[0].__dict__)
    # ------- convert back to df, filter out non-observables
    candidateDf = Candidate.candidatesToDf(candidates)
    if "Rejected Reason" in candidateDf.columns:
        candidateDf = candidateDf.loc[candidateDf["RejectedReason"].isna()].sort_values(by=["Magnitude"],
                                                                                        ascending=True)
    # ------- save to observable.csv, astrophotography's version of a database
    candidateDf.to_csv(PATH_TO(join("schedulerConfigs","Astrophotography","observable.csv")), index=None)  # self-locating uncertainty

if __name__ == "__main__":
    update_database(None)