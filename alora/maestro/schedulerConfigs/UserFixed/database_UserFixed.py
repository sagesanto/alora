import configparser
from datetime import datetime as datetime, timedelta
import os, sys
import astropy.units as u
import pandas as pd
from os.path import join, dirname
from astral import LocationInfo

from alora.config import observatory_location

try:
    grandparentDir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir))
    sys.path.append(grandparentDir)
    from alora.maestro.scheduleLib import genUtils, candidateDatabase
    from alora.maestro.scheduleLib.candidateDatabase import Candidate, CandidateDatabase
    from alora.maestro.scheduleLib.genUtils import stringToTime, TypeConfiguration, Config

    sys.path.remove(grandparentDir)
    genConfig = genUtils.Config(os.path.join(grandparentDir, "files", "configs", "config.toml"))

except ImportError:
    from alora.maestro.scheduleLib import genUtils
    from alora.maestro.scheduleLib.genUtils import stringToTime, TypeConfiguration, Config
    from alora.maestro.scheduleLib.candidateDatabase import Candidate, CandidateDatabase

    genConfig = genUtils.Config(os.path.join("files", "configs", "config.toml"))

location = observatory_location

uConfig = Config(join(dirname(__file__), "config.toml"))

def updateCandidate(candidate: Candidate, dbConnection: CandidateDatabase):
    dbConnection.editCandidateByID(candidate.ID, candidate.asDict())


def evalObservability(candidates):
    sunrise, sunset = genUtils.get_sunrise_sunset()
    return [c.evaluateStaticObservability(sunset, sunrise, minHoursVisible=1, locationInfo=location) for c in
            candidates]

def update_database(dbPath):
    print("Updating UserFixed targets")
    dbConnection = CandidateDatabase(dbPath, "UserFixed Database Agent")
    candidates = dbConnection.table_query("Candidates", "*",
                                          "RemovedReason IS NULL AND CandidateType IS \"UserFixed\"",
                                          [], returnAsCandidates=True)
    if not candidates:
        print("No UserFixed targets to update.")
        return
    candidates = evalObservability(candidates)
    for c in candidates:
        updateCandidate(c, dbConnection)

if __name__ == "__main__":
    update_database(sys.argv[1])
