# one-time code conversion. does not need to be run ever again.
from sqlalchemy import text
import scheduleLib.db.dbConfig as dbConfig
from scheduleLib.db.db_models import Observation, CandidateModel, ProcessingCode

session = dbConfig.candidate_db_session

observations = session.query(Observation).all()
for obs in observations:
    if obs.ProcessingCodesCol:
        codes = [c for c in obs.ProcessingCodesCol.split(',') if c] 
        for code in codes:
            c = int(code)
            if c != 0:
                c = session.query(ProcessingCode).filter(ProcessingCode.Code == code).first()
                if c:
                    print(f"Processing code {code} found in database, adding to observation {obs.ObservationID}")
                    obs.ProcessingCode.append(c)
        session.commit()
    