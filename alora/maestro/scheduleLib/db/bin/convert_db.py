# Sage Santomenna 2025
# convert the database from a single table to a multi-table structure according to the schema
import sys, os
import json
from os.path import abspath, dirname, join
from alora.config import configure_logger, logging_config_path
from alora.maestro.scheduleLib.db.bin.create_db import create_db
from alora.maestro.scheduleLib.db.dbConfig import configure_db
from alora.maestro.scheduleLib.candidateDatabase import CandidateDatabase, Candidate
from alora.maestro.scheduleLib.db.db_models import (
    CandidateModel,
    Info,
    ObservingCfg,
    SchedulingCfg,
)


def convert_db(old_path: str, new_path: str):
    old_db = CandidateDatabase(old_path, "DbConverter")
    create_db(new_path)
    session, _ = configure_db(new_path)
    candidates = old_db.table_query(
        "Candidates", columns="*", condition="1=1", values=[], returnAsCandidates=False
    )
    for c in candidates:
        cmodel = CandidateModel(
            ID=c.get("ID"),
            Author=c.get("Author"),
            DateAdded=c.get("DateAdded"),
            DateLastEdited=c.get("DateLastEdited"),
            CandidateName=c.get("CandidateName"),
            Priority=c.get("Priority"),
            CandidateType=c.get("CandidateType"),
            SchedulingType="standard",
            Updated=c.get("Updated"),
            StartObservability=c.get("StartObservability"),
            EndObservability=c.get("EndObservability"),
            TransitTime=c.get("TransitTime"),
            RejectedReason=c.get("RejectedReason"),
            RemovedReason=c.get("RemovedReason"),
            RemovedDt=c.get("RemovedDt"),
            RA=c.get("RA"),
            Dec=c.get("Dec"),
            Magnitude=c.get("Magnitude")
        )
        s_cfg_d = {"NumExposures": c.get("NumExposures"), "ExposureTime": c.get("ExposureTime")}
        cmodel.SchedulingCfg = SchedulingCfg(cfg=json.dumps(s_cfg_d))
        o_cfg_d = {"Filter": c.get("Filter"), "Guide": c.get("Guide")}
        cmodel.ObservingCfg = ObservingCfg(cfg=json.dumps(o_cfg_d))
        for i in range(1,11):
            k = f"CVal{i}"
            v = c.get(k)
            if v is not None:
                cmodel.Info.append(Info(Key=k, Value=v))
        for k in ["dRA","dDec","RMSE_RA","RMSE_Dec","Score","ApproachColor"]:
            v = c.get(k)
            if v is not None:
                cmodel.Info.append(Info(Key=k, Value=v))
        session.add(cmodel)
    session.commit()

def main():
    old_path = abspath(sys.argv[1])
    new_path = abspath(sys.argv[2])
    convert_db(old_path, new_path)


if __name__ == "__main__":
    main()
