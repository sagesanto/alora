# Sage Santomenna 2023
# read in a metadata db and a schedule, log observations in Maestro db

import os, sqlite3, logging
from sqlite3 import DatabaseError
from alora.maestro.scheduleLib.genUtils import query_to_dict
import scheduleLib.db.dbConfig as dbConfig
from alora.maestro.scheduleLib.db.db_models import Observation, CandidateModel
from alora.maestro.scheduleLib.schedule import Schedule, AutoFocus


def process_metadata(metadata_db_path, start, end, candidate_name):
    conn = sqlite3.connect(metadata_db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # take the start time, a datetime object, and find the closest capture start time (a unix timestamp) to it in the database
    c.execute(f"SELECT * FROM DatasetMetaData WHERE AcqTimestamp >= {start.timestamp()} AND Description NOT LIKE '%Re-Center%' ORDER BY AcqTimestamp ASC LIMIT 1")
    rows = c.fetchall()
    if len(rows) == 0:
        raise DatabaseError(f"No metadata found for {candidate_name}")
    row = query_to_dict(rows)[0]
    capture_start_epoch = row["AcqTimestamp"]
    dataset = row["Name"]
    system_name = row["SystemName"]
    camera_name = row["CameraName"]
    encoderRA = round(float(row["TelescopeRA"]),5)
    encoderDec = round(float(row["TelescopeDEC"]),5)
    return capture_start_epoch, dataset, encoderRA, encoderDec, system_name, camera_name


def process_obs_log(obs_log_path):
    obs_data = {}
    current_set = {}
    target_name = "No Name!"

    with open(obs_log_path, "r") as f:
        for line in f.readlines():
            line = line.replace("\n","").replace("[","").replace("]","")
            if "Target name" in line:
                target_name = line.split(": ")[1].strip()
                current_set["target_name"] = target_name
            if "Telescope Offset" in line:
                tup = line.split(": ")[1].strip().split(", ") # deg
                current_set["offset_ra"] = float(tup[0])
                current_set["offset_dec"] = float(tup[1].split(" ")[0])
                current_set["astrometry_status"] = 1
            if "Sky background" in line:
                current_set["sky_background"] = float(line.split(": ")[1].split(" ")[0].strip())
            if "Telescope focus" in line:
                current_set["focus"] = float(line.split(": ")[1].split(" ")[0].strip())
            if "temperature" in line:
                try:
                    current_set["temperature"] = float(line.split("=  ")[1].split(" ")[0].strip()) # celsius
                except:
                    current_set["temperature"] = float(line.split(": ")[1].split(" ")[0].strip()) # celsius
            if "Astrometry failed" in line:
                current_set["astrometry_status"] = -1
            if "Exposed for" in line:
                obs_data[target_name] = current_set
                current_set = {"astrometry_status": 0}
                target_name = "No Name!"
    obs_data[target_name] = current_set
    return obs_data

class ObsLogger:
    def __init__(self):
        self.db_session = dbConfig.dbSession
        # self.cand_db = CandidateDatabase(cand_db_path, "ObsLogger")

    def _log_obs(self, obs: Observation):
        self.db_session.add(obs)
        self.db_session.commit()
    
    def log_obs(self, **kwargs):
        obs = Observation(**kwargs)
        self._log_obs(obs)
    
    def log_from_schedule(self, schedule_path, obs_log_path=None,metadata_db_path=None):
        if obs_log_path is None:
            obs_log_path = os.path.join(os.path.dirname(schedule_path),"obs.log")
        if metadata_db_path is None:
            metadata_db_path = os.path.join(os.path.dirname(schedule_path),"Metadata.db")
        obs_data = process_obs_log(obs_log_path)
        schedule = Schedule.read(schedule_path)
        obs_dicts = []
        # print("Obs Data: ", obs_data)

        for obs in [t for t in schedule.tasks if not isinstance(t, AutoFocus)]:
            obs_dict = {}
            # print(int(obs.candidate_ID))
            # c = self.db_session.query(CandidateModel).filter(CandidateModel.ID == int(obs.candidate_ID)).first()
            # if c is None:
            #     logging.warning(f"Could not find candidate {obs.candidate_ID} in database")
            #     continue
            # look up by name instead
            c = self.db_session.query(CandidateModel).filter(CandidateModel.CandidateName == obs.targetName).first()
            if c is None:
                logging.warning(f"Could not find candidate {obs.targetName} in database")
                continue
            # obs_dict["CandidateID"] = c.ID
            try:
                obs_dict["RA"], obs_dict["Dec"] = round(c.RA, 5), round(c.Dec,5)
            except:
                print("No RA/Dec for ", c.CandidateName)
                continue
            obs_dict["RMSE_RA"], obs_dict["RMSE_Dec"] = round(c.RMSE_RA,2) if c.RMSE_RA is not None else None, round(c.RMSE_Dec,2) if c.RMSE_Dec is not None else None
            obs_dict["ApproachColor"] = c.ApproachColor
            start, end = obs.startTime, obs.endTime
            obs_dict["ExposureTime"] = obs.exposureTime
            try:
                obs_dict["CaptureStartEpoch"], obs_dict["Dataset"], obs_dict["EncoderRA"], obs_dict["EncoderDec"], obs_dict["SystemName"], obs_dict["CameraName"] = process_metadata(metadata_db_path, start, end, c.CandidateName)
            except DatabaseError as e:
                print("Error processing metadata for ", c.CandidateName,e)
                continue
            splitname = obs_dict["Dataset"].split("_")
            if len(str(splitname[1])) == 1:
                dataname = f"{splitname[0]}_{splitname[1]}"
            else:
                dataname = splitname[0]
            if 'recenter' in dataname.lower():
                continue
            if dataname in obs_data:
                obs_dict["RAOffset"] = round(obs_data[dataname].get("offset_ra", 19229),5)
                obs_dict["DecOffset"] = round(obs_data[dataname].get("offset_dec", 19229),5)
                obs_dict["SkyBackground"] = obs_data[dataname].get("sky_background",-1)
                obs_dict["Focus"] = obs_data[dataname].get("focus", -1)
                obs_dict["Temperature"] = obs_data[dataname].get("temperature", 19229)
                obs_dict["AstrometryStatus"] = obs_data[dataname]["astrometry_status"]
            else:
                print("No data for ", dataname)
                obs_dict["RAOffset"] = 19229
                obs_dict["DecOffset"] = 19229
                obs_dict["SkyBackground"] = -1
                obs_dict["Focus"] = -1
                obs_dict["Temperature"] = 19229
                obs_dict["AstrometryStatus"] = 0
            obs_dict["ProcessingCode"] = 0
            obs_dict["Submitted"] = 0
            obs_dicts.append(obs_dict)
            obs = Observation(**obs_dict)
            self.db_session.add(obs)
            c.Observations.append(obs)
            self.db_session.commit()
        return obs_dicts
        # now we make an observation object from this dictionary and associate it with the candidate c
    
if __name__ == "__main__":
    import pandas as pd
    obs_log_path = "files/misc_and_records/obsLoggerTest/20231207/obs.log"
    metadata_db_path = "files/misc_and_records/obsLoggerTest/20231207/Metadata.db"
    schedule_file_path = "files/misc_and_records/obsLoggerTest/20231207/Scheduler.txt"
    # rows = process_obs_log(obs_log_path)
    # df = pd.DataFrame(rows.values())
    # print(df)
    obs_logger = ObsLogger()
    obs_dicts = obs_logger.log_from_schedule(schedule_file_path, obs_log_path, metadata_db_path)
    df = pd.DataFrame(obs_dicts)
    print(df)
    # df.to_csv("files/misc_and_records/obsLoggerTest/out_log.csv")