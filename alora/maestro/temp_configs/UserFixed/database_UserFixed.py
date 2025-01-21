import configparser
from datetime import datetime as datetime, timedelta
import os, sys
import astropy.units as u
import pandas as pd
from astral import LocationInfo

try:
    grandparentDir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir))
    sys.path.append(grandparentDir)
    from scheduleLib import genUtils, candidateDatabase
    from scheduleLib.candidateDatabase import Candidate, CandidateDatabase
    from scheduleLib.genUtils import stringToTime, TypeConfiguration, genericScheduleLine

    sys.path.remove(grandparentDir)
    genConfig = configparser.ConfigParser()
    genConfig.read(os.path.join(grandparentDir, "files", "configs", "config.txt"))
    uConfig = configparser.ConfigParser()
    uConfig.read(os.path.join(grandparentDir, "files", "configs", "userFixed_config.txt"))

except ImportError:
    from scheduleLib import genUtils
    from scheduleLib.genUtils import stringToTime, TypeConfiguration, genericScheduleLine
    from scheduleLib.candidateDatabase import Candidate, CandidateDatabase

    genConfig = configparser.ConfigParser()
    genConfig.read(os.path.join("files", "configs", "config.txt"))
    uConfig = configparser.ConfigParser()
    uConfig.read(os.path.join("files", "configs", "userFixed_config.txt"))

genConfig = genConfig["DEFAULT"]
uConfig = uConfig["DEFAULT"]

location = LocationInfo(name=genConfig["obs_name"], region=genConfig["obs_region"], timezone=genConfig["obs_timezone"],
                        latitude=genConfig.getfloat("obs_lat"),
                        longitude=genConfig.getfloat("obs_lon"))


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
