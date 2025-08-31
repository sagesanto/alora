# Sage Santomenna 2023
from datetime import datetime

import pytz
from astral import LocationInfo
from astropy.time import Time
import astropy.units as u
from alora.maestro.scheduleLib.candidateDatabase import Candidate
from astropy.coordinates import Angle
from alora.maestro.scheduleLib import genUtils

PST = timezone=pytz.timezone('US/Pacific')

obsName = "TMO"
region = "CA, USA"
obsTimezone = "UTC"
obsLat = 34.36
obsLon = -117.63
TMOlocation = LocationInfo(name=obsName, region=region, timezone=obsTimezone, latitude=obsLat,
                           longitude=obsLon)

def evalObservability(candidates):
    sunrise, sunset = genUtils.get_sunrise_sunset()
    return [c.evaluateStaticObservability(sunset, sunrise, minHoursVisible=0.1, locationInfo=TMOlocation) for c in
            candidates]

if __name__ == "__main__":
    targets = [
        ("Target 1", Angle("15h21m10s"), Angle("-15d31m")),
        ("Target 2", Angle("18h33m37s"), Angle("-21d36m")),
        ("Target 3", Angle("20h01m55s"), Angle("-23d16m")),
        ("Target 4", Angle("20h55m30s"), Angle("-13d47m")),
        ("Jupiter", Angle("02h52m40.9s"), Angle("15d07m12.1s")),
        ("Saturn", Angle("22h16m"), Angle("-12.6",unit=u.deg)),
        ("Mars", Angle("12h26m"), Angle("-2.2", unit=u.deg))
    ]
    
    candidates = []
    for target in targets:
        c = Candidate.fromDictionary({"CandidateName": target[0], "CandidateType": "util", "RA": target[1].hour, "Dec": target[2]})
        candidates.append(c)

    o = evalObservability(candidates)
    for c in o:
        c.StartObservability = genUtils.timeToString((pytz.UTC.localize(genUtils.stringToTime(c.StartObservability))).astimezone(PST))
        c.EndObservability = genUtils.timeToString((pytz.UTC.localize(genUtils.stringToTime(c.EndObservability))).astimezone(PST))
        print(f"{c.CandidateName} is observable between {c.StartObservability} PST and {c.EndObservability} PST")
