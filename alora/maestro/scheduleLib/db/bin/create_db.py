# Sage Santomenna 2023, 2025
# create/recreate the appropriately-structured maestro database
 
import sys, os
import sqlite3
from alora.maestro.scheduleLib.db.dbConfig import configure_db
from sqlalchemy.schema import CreateTable
from alora.maestro.scheduleLib.db.db_models import CandidateModel, Info, ObservingCfg, SchedulingCfg, Observation, ProcessingCode, ObservationCodeAssociation, codes
from sqlalchemy import text

def main():
    path = os.path.abspath(sys.argv[1])
    create_db(path)

def create_db(path):
    session, engine = configure_db(path)
    candidate_stmt = CreateTable(CandidateModel.__table__, if_not_exists=True).compile(engine)
    info_stmt = CreateTable(Info.__table__, if_not_exists=True).compile(engine)
    observing_cfg_stmt = CreateTable(ObservingCfg.__table__, if_not_exists=True).compile(engine)
    scheduling_cfg_stmt = CreateTable(SchedulingCfg.__table__, if_not_exists=True).compile(engine)
    observation_stmt = CreateTable(Observation.__table__, if_not_exists=True).compile(engine)
    processing_stmt = CreateTable(ProcessingCode.__table__, if_not_exists=True).compile(engine)

    session.execute(text(str(candidate_stmt)))
    session.execute(text(str(info_stmt)))
    session.execute(text(str(observing_cfg_stmt)))
    session.execute(text(str(scheduling_cfg_stmt)))
    session.execute(text(str(observation_stmt)))
    session.execute(text(str(processing_stmt)))
    session.commit()
    association_stmt = CreateTable(ObservationCodeAssociation, if_not_exists=True).compile(engine)
    session.execute(text(str(association_stmt)))

    for code, description in codes.items():
        try:
            session.add(ProcessingCode(Code=code, Description=description))
            session.commit()
            print(f"Added code {code} to database")
        except Exception as e:
            session.rollback()
        # print("error:",e)

if __name__ == "__main__":
    main()