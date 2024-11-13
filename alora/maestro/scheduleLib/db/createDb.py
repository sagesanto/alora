# Sage Santomenna 2023
# create/recreate the appropriately-structured maestro database
 
import sqlite3, os
from dbConfig import engine, dbSession
from sqlalchemy.schema import CreateTable
from db_models import CandidateModel, Observation, ProcessingCode, ObservationCodeAssociation, codes
from sqlalchemy import text

candidate_stmt = CreateTable(CandidateModel.__table__, if_not_exists=True).compile(engine)
observation_stmt = CreateTable(Observation.__table__, if_not_exists=True).compile(engine)
processing_stmt = CreateTable(ProcessingCode.__table__, if_not_exists=True).compile(engine)

dbSession.execute(text(str(candidate_stmt)))
dbSession.execute(text(str(observation_stmt)))
dbSession.execute(text(str(processing_stmt)))
dbSession.commit()
association_stmt = CreateTable(ObservationCodeAssociation, if_not_exists=True).compile(engine)
dbSession.execute(text(str(association_stmt)))

for code, description in codes.items():
    try:
        dbSession.add(ProcessingCode(Code=code, Description=description))
        dbSession.commit()
        print(f"Added code {code} to database")
    except Exception as e:
        dbSession.rollback()
        # print("error:",e)

# print(candidate_stmt)
# print(observation_stmt)

# def createDatabase(dbPath):
#     con = sqlite3.connect(dbPath)
#     cur = con.cursor()

#     cur.execute(
#         """
#         CREATE TABLE IF NOT EXISTS "Candidates" (
#         "Author"	TEXT NOT NULL,
#         "DateAdded"	TEXT NOT NULL,
#         "DateLastEdited"	TEXT,
#         "CandidateName"	TEXT NOT NULL,
#         "Priority"	INTEGER NOT NULL,
#         "CandidateType"	TEXT NOT NULL,
#         "Updated"	TEXT,
#         "StartObservability"	TEXT,
#         "EndObservability"	TEXT,
#         "TransitTime"	TEXT,
#         "RejectedReason"	TEXT,
#         "RemovedReason"	TEXT,
#         "RemovedDt"	TEXT,
#         "RA"	REAL,
#         "Dec"	REAL,
#         "dRA"	NUMERIC,
#         "dDec"	NUMERIC,
#         "Magnitude"	REAL,
#         "RMSE_RA"	REAL,
#         "RMSE_Dec"	REAL,
#         "nObs"	INTEGER,
#         "Score"	INTEGER,
#         "ApproachColor"	TEXT,
#         "ExposureTime"	NUMERIC,
#         "NumExposures"	INTEGER,
#         "Scheduled"	INTEGER DEFAULT 0,
#         "Observed"	INTEGER DEFAULT 0,
#         "Processed"	NUMERIC DEFAULT 0,
#         "Submitted"	INTEGER DEFAULT 0,
#         "Notes"	TEXT,
#         "ID"	INTEGER,
#         "CVal1"	BLOB,
#         "CVal2"	BLOB,
#         "CVal3"	BLOB,
#         "CVal4"	BLOB,
#         "CVal5"	BLOB,
#         "CVal6"	BLOB,
#         "CVal7"	BLOB,
#         "CVal8"	BLOB,
#         "CVal9"	BLOB,
#         "CVal10"	BLOB,
#         "Filter"	TEXT,
#         "Guide"	INTEGER DEFAULT 1,
#         PRIMARY KEY("ID" AUTOINCREMENT)
#     )"""
#     )

#     cur.execute("""
#     CREATE TABLE IF NOT EXISTS "Observation" (
#         "CandidateID" INTEGER,
#         "ObservationID" INTEGER NOT NULL UNIQUE,
#         "RMSE_RA" NUMERIC,
#         "RMSE_Dec" NUMERIC,
#         "RA" NUMERIC,
#         "Dec" NUMERIC,
#         "ApproachColor" TEXT,
#         "AstrometryStatus" TEXT,
#         "ExposureTime" NUMERIC,
#         "EncoderRA" NUMERIC,
#         "EncoderDec" NUMERIC,
#         "SkyBackground" NUMERIC,
#         "Temperature" NUMERIC,
#         "Dataset" TEXT,
#         "CaptureStartEpoch" NUMERIC,
#         "RAOffset" NUMERIC,
#         "DecOffset" NUMERIC,
#         "ProcessingCode" INTEGER NOT NULL,
#         "Submitted" INTEGER NOT NULL,
#         "Comments" TEXT,
#         PRIMARY KEY (CandidateID, ObservationID),
#         FOREIGN KEY(CandidateID) REFERENCES "Candidates"(ID)
#     )""")

# if __name__ == "__main__":
#     dbpath = "C:\\Users\\chell\\PycharmProjects\\sqlalchemy\\maestro\\files\\misc_and_records\\obsLoggerTest\\candidate_database_20240113.db"
#     print(os.path.exists(os.path.abspath(dbpath)))
#     createDatabase(dbpath)



# Assuming `CandidateModel` is your SQLAlchemy model
