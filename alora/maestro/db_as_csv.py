import pandas as pd, sys, os
from scheduleLib.candidateDatabase import Candidate, CandidateDatabase
from datetime import datetime
from scheduleLib.genUtils import query_to_dict
from sqlite3 import DatabaseError, connect, Row, OperationalError

if len(sys.argv) != 2:
    raise ValueError("Please provide a path to a database file")

db_path = sys.argv[1]

if not os.path.exists(db_path):
    raise FileNotFoundError(f"Could not find {db_path}")

candidateDb = CandidateDatabase(db_path, "Target Stats Query")

candidateDb.db_cursor.execute("SELECT * FROM Candidates")

candidates = candidateDb.queryToCandidates(candidateDb.db_cursor.fetchall())

df = Candidate.candidatesToDf(candidates)
tstamp = datetime.utcnow().strftime('%Y%m%d')
df.to_csv(f"files/db_csvs/candidates_{tstamp}.csv", index=False)

# now get observations
try:
    candidateDb.db_cursor.execute("SELECT * FROM Observation")
    conn = connect(db_path)
    conn.row_factory = Row
    c = conn.cursor()
    c.execute("SELECT * FROM Observation")
    rows = c.fetchall()
    if len(rows) == 0:
        raise OperationalError(f"No observations found in db {db_path}")
    obs = query_to_dict(rows)
    df = pd.DataFrame(obs)
    df.to_csv(f"files/db_csvs/observations_{tstamp}.csv", index=False)
except OperationalError as e:
    print("No observations found in db")
    print(e)
