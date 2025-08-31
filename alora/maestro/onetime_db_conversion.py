# Go through the candidate database and convert ra values from decimal hours to decimal degrees
# does not need to be run ever again.
import sys, os
# sys.path.append("C:\\Users\\chell\\PycharmProjects\\stneo\\tmocass")
from alora.maestro.scheduleLib.candidateDatabase import CandidateDatabase
from astropy.coordinates import Angle
from configparser import ConfigParser
print(os.getcwd())
dbpath = "C:\\Users\\chell\\PycharmProjects\\sqlalchemy\\maestro\\files\\misc_and_records\\obsLoggerTest\\candidate_database_20240113.db"
db = CandidateDatabase(dbpath,"DB Angle Conversion")

rows = db.table_query("Candidates",columns="*", condition="",values=[], returnAsCandidates=False)

print([r.get("RA",None) for r in rows])
# ra is currently in decimal hours and must be converted to decimal degrees
for r in rows:
    ra = r.get("RA",None)
    if ra is not None:
        r["RA"] = Angle(r["RA"],unit="hour").degree

for row in rows:
    db.editCandidateByID(ID=row["ID"],updateDict=row)

rows = db.table_query("Candidates",columns="*", condition="",values=[], returnAsCandidates=False)

print([r.get("RA",None) for r in rows])