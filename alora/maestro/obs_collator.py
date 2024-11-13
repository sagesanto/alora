# Sage Santomenna 2023
# combine observations gleaned from system files with observation records

import pandas as pd, sys, os
from scheduleLib.db.dbConfig import dbSession
from scheduleLib.db.db_models import Observation
from datetime import datetime
df = pd.read_csv("files/misc_and_records/all_processed.csv")

# for each observation in the df, get the corresponding observation record from the database. 
#    to do this, we need to get the candidate name, the start time, and the end time
#    then we can query the database for the observation record that has the candidate name in its dataset name
#    and whose start epoch is between the start and end times of the observation (to deduplicate by name)

df["obs_id"] = [None for i in range(len(df))]
for i, row in df.iterrows():
    candidate_name = row["MPC Target"]
    first = True
    if "_2" in candidate_name:
        first=False
    # candidate_name = candidate_name.split("_")[0]
    start_epoch = datetime.strptime(row["start"],'%Y-%m-%d').timestamp()
    end_epoch = datetime.strptime(row["end"],'%Y-%m-%d').timestamp() + 86400/2
    obs_record = dbSession.query(Observation).filter(Observation.Dataset.like(f"%{candidate_name}%")).filter(Observation.CaptureStartEpoch.between(start_epoch, end_epoch)).first()
    # if first:
    # else:
    #     try:
    #         print("trying to find second obs record for ", candidate_name)
    #         r = dbSession.query(Observation).filter(Observation.Dataset.like(f"%{candidate_name}%")).filter(Observation.CaptureStartEpoch.between(start_epoch, end_epoch)).all()
    #         obs_record = r[1]
    #         print("found second obs record for ", candidate_name)
    #     except:
    #         obs_record = None
    if obs_record is None:
        print(f"Could not find observation record for {candidate_name} between {start_epoch} and {end_epoch}")
        continue
    # if obs_record.ObservationID in df["obs_id"].unique():
    #     print(f"Found duplicate observation record ({obs_record.ObservationID}) for {candidate_name} between {start_epoch} and {end_epoch}")
    #     continue
    print(f"Found observation record for {candidate_name} between {start_epoch} and {end_epoch}")
    df.loc[i, "obs_id"] = obs_record.ObservationID
    obs_record.ProcessingCodes = row["codes"]
    obs_record.Submitted = row["Submitted"]
    dbSession.commit()

df.to_csv("files/misc_and_records/all_processed_with_obs_ids.csv")
print(f"Found {len(df.dropna(subset=['obs_id']))} observations out of {len(df)}")
print(len(df.dropna(subset=["obs_id"])["obs_id"].unique()),"corresponded to unique observations")
print(df.dropna(subset=["obs_id"])[["obs_id", "MPC Target", "start", "end"]])

# # now find obs in database that don't appear in the log file (their obs_id is None)
missing = df[df["obs_id"].isna()]
obs = dbSession.query(Observation).all()
found = 0
for ob in obs:
    if ob.ObservationID not in df["obs_id"].unique():
        if ob.Dataset.split("_")[0]+"_1" in missing["MPC Target"].unique() or ob.Dataset.split("_")[0]+"_2" in missing["MPC Target"].unique():
            found += 1
#             print(ob.ObservationID, ob.Dataset, ob.CaptureStartEpoch)
#             print("found in log file: ",missing[missing["MPC Target"]==ob.Dataset.split("_")[0]+"_1"][["start","end"]].values[0])
print(f"could possibly recover {found} observations from the database")