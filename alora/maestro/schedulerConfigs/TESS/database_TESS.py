import configparser
from datetime import datetime as datetime, timedelta
import os, sys, glob
import astropy.units as u
from astropy.coordinates import Angle
import pandas as pd
from astral import LocationInfo
import numpy as np
import pytz
import logging

try:
    grandparentDir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir))
    sys.path.append(grandparentDir)
    from scheduleLib import genUtils, candidateDatabase
    from scheduleLib.candidateDatabase import Candidate, CandidateDatabase
    from scheduleLib.genUtils import stringToTime, TypeConfiguration, genericScheduleLine, overlapping_time_windows

    sys.path.remove(grandparentDir)
    genConfig = configparser.ConfigParser()
    genConfig.read(os.path.join(grandparentDir, "files", "configs", "config.txt"))
    tConfig = configparser.ConfigParser()
    tConfig.read(os.path.join(grandparentDir, "files", "configs", "tess_config.txt"))

except ImportError:
    from scheduleLib import genUtils
    from scheduleLib.genUtils import stringToTime, TypeConfiguration, genericScheduleLine, overlapping_time_windows
    from scheduleLib.candidateDatabase import Candidate, CandidateDatabase

    genConfig = configparser.ConfigParser()
    genConfig.read(os.path.join("files", "configs", "config.txt"))
    tConfig = configparser.ConfigParser()
    tConfig.read(os.path.join("files", "configs", "tess_config.txt"))

genConfig = genConfig["DEFAULT"]
tConfig = tConfig["DEFAULT"]

location = LocationInfo(name=genConfig["obs_name"], region=genConfig["obs_region"], timezone=genConfig["obs_timezone"],
                        latitude=genConfig.getfloat("obs_lat"),
                        longitude=genConfig.getfloat("obs_lon"))

logger = logging.getLogger("TESS Database Agent")

def write_out(*args):
    logging.info(" ".join(str(a) for a in args))
    # sys.stdout.write(" ".join([str(x) for x in args]) + "\n")
    # sys.stdout.flush()

def updateCandidate(candidate: Candidate, dbConnection: CandidateDatabase):
    dbConnection.editCandidateByID(candidate.ID, candidate.asDict())
    dbConnection.clear_invalid_status(candidate.ID)

def calc_num_frames(start_obs, end_obs, exptime):
    if not start_obs or not end_obs or pd.isnull(start_obs) or pd.isnull(end_obs):
        return -1
    return int(np.ceil((end_obs - start_obs).total_seconds() / exptime)) # - 5*int(np.ceil(60/exptime)) # need to subtract off for scheduler reasons


# to deal with multiple of the same planet in different (or the same) CSVs (because of multiple transits),
# we will need to load each csv into one big dataframe, then de-duplicate by choosing the next transit of each that
# has not already occcurred. then, if the candidate is new we'll add it to the database, if it's already in the database
# we'll update it with the new transit info.
def make_csv_candidates(csv_names): 
    """
    Read CSVs in the list of csv_names and return a list of Candidate objects. Calculates observability, considering both
    the transit window and the observability window on the night of the transit.
    Does not set the ID of the candidate (performed later) or do any database operations.
    """
    master_df = pd.concat([pd.read_csv(f, dtype={'TOI': str}) for f in csv_names])
    
    master_df = master_df.rename(columns={"TOI": "CandidateName", "Vmag": "Magnitude"})
    master_df["CandidateName"] = master_df["CandidateName"].apply(lambda v: f"{'TOI' if len(v)<=7 else 'TIC'} {v}")
    # calculate ingress or egress time +- obs_buffer into new column "obs_window"
    obs_buffer = tConfig.getint("obs_buffer")

    jd_to_dt = np.vectorize(genUtils.jd_to_dt)
    tts = np.vectorize(genUtils.timeToString)

    master_df["ingress_dt"] = jd_to_dt(master_df["pl_ingress"])
    master_df["egress_dt"] = jd_to_dt(master_df["pl_egress"])
    master_df["pl_obs_start"] = tts(master_df["ingress_dt"] - timedelta(minutes=obs_buffer))
    master_df["pl_obs_end"] = tts(master_df["egress_dt"] + timedelta(minutes=obs_buffer))
    master_df["pl_dur_in_min"] = [
        (e - i).seconds / 60
        for e, i in zip(master_df["egress_dt"], master_df["ingress_dt"])
    ]
    master_df["pl_dur_in_min_buffered"] = master_df["pl_dur_in_min"] + 2 * obs_buffer

    colToCVal = {
        "pl_obs_start": "CVal1",
        "pl_obs_end": "CVal2",
        "NightOfTransit": "CVal3",
        "pl_ingress": "CVal4",  # this is in julian day
        "pl_egress": "CVal5",
        "pl_dur_in_min": "CVal6",
        "pl_dur_in_min_buffered": "CVal7",
        "pl_orbper": "CVal8",
        "Jmag": "CVal9",
        "TransitDepth(ppm)": "CVal10",
    }

    # remove candidates that already transited
    master_df = master_df[master_df["egress_dt"] > datetime.now(tz=pytz.UTC)]

    # sort by next transit
    master_df = master_df.sort_values(by="ingress_dt", ascending=True)

    # remove duplicates
    master_df = master_df.drop_duplicates(subset="CandidateName", keep="first")
    if not len(master_df):
        write_out("No TESS candidates in CSVs are found to be valid.")
        return []

    # now, we need to find the observability of these candidates. 
    # this is the AND of the transit window and the candidate's observability window on the night of the transit
    master_df[["RA_obs_start", "RA_obs_end"]] = master_df.apply(lambda row: genUtils.static_observability_window(row.RA, row.Dec, row.ingress_dt), axis=1, result_type='expand')
    master_df[["StartObservability", "EndObservability"]] = master_df.apply(lambda row: overlapping_time_windows(row["ingress_dt"] - timedelta(minutes=obs_buffer), row["egress_dt"] + timedelta(minutes=obs_buffer), row["RA_obs_start"], row["RA_obs_end"]), axis=1, result_type="expand")

    for _, row in master_df.iterrows():
        if row["StartObservability"] and not pd.isnull(row["StartObservability"]):
            if not row["EndObservability"] or pd.isnull(row["EndObservability"]):
                logger.error(f"Problem row: {row}")
                raise ValueError(f"Candidate {row['CandidateName']} has StartObservability but no EndObservability. This should not happen.")
            if row["StartObservability"] < row["ingress_dt"] - timedelta(minutes=obs_buffer):
                logger.error(f"Problem row: {row}")
                raise ValueError(f"Candidate {row['CandidateName']} has StartObservability before ingress. This should not happen.")
            if row["EndObservability"] > row["egress_dt"] + timedelta(minutes=obs_buffer):
                logger.error(f"Problem row: {row}")
                raise ValueError(f"Candidate {row['CandidateName']} has EndObservability after egress. This should not happen.")

    master_df["ExposureTime"] = [tConfig.getfloat("EXPTIME")] * len(master_df.index)
    master_df["NumExposures"] = master_df.apply(lambda row: calc_num_frames(row.StartObservability,row.EndObservability,tConfig.getfloat("EXPTIME")), axis=1) # need to subtract off for scheduler reasons
    master_df["Filter"] = [tConfig.get("FILTER")] * len(master_df.index)
    master_df.rename(columns=colToCVal, inplace=True)
    master_df.drop(
        columns=["ingress_dt", "egress_dt", "pl_tranmid", "pl_trandur", "RA_obs_start", "RA_obs_end"], inplace=True
    )

    master_df = master_df.reset_index(drop=True)
    candidates = []
    for i, row in master_df.iterrows():
        d = {}
        for j in ["RA", "Dec"]:
            d[j] = Angle(float(row[j]), unit=u.deg)
        d["Magnitude"] = float(row["Magnitude"])
        d["Priority"] = int(row["Priority"])

        for col, cval in row.items():
            d[col] = cval
        del d["CandidateName"]
        candidates.append(Candidate(row["CandidateName"], "TESS", **d))

    # for c in candidates:
    #     write_out(f"Candidate {c.CandidateName} with RA {c.RA/(15*u.deg)}h becomes observable at {c.StartObservability}.")
    
    return candidates


# check to see if we have a new CSV in the directory, if so, run populate_TESS
def update_and_insert(csv_candidates, dbConnection):
    """
    Update the database with the new candidates from the CSV file. If a candidate already exists in the database, update it with the new information. If a candidate is new, insert it into the database.
    ASSUMES CANDIDATES WITH THE SAME NAME REFER TO THE SAME OBJECT
    """

    write_out("Checking against existing candidates in database...")
    for c in csv_candidates:
        ec = dbConnection.getCandidateByName(c.CandidateName)
        if not ec:
            c.StartObservability = genUtils.timeToString(c.StartObservability, shh=True)
            c.EndObservability = genUtils.timeToString(c.EndObservability, shh=True)
            dbConnection.insertCandidate(c)
            write_out(f"New TESS Candidate: {c.CandidateName}")
            continue
        if len(ec) > 1:
            raise ValueError(f"Multiple candidates with name {c.CandidateName} in database. Aborting.")
        ec = ec[0]
        if not ec.hasField("StartObservability") or not ec.hasField("EndObservability"):
            write_out(f"Existing candidate for {ec.CandidateName} did not have StartObservability and EndObservability. Updating.")
            c.StartObservability = genUtils.timeToString(c.StartObservability, shh=True)
            c.EndObservability = genUtils.timeToString(c.EndObservability, shh=True)
            c.ID = ec.ID
            updateCandidate(ec, dbConnection)
            continue

        ec_start = stringToTime(ec.StartObservability).replace(tzinfo=pytz.UTC) 
        ec_end = stringToTime(ec.EndObservability).replace(tzinfo=pytz.UTC) 

        if (c.StartObservability < ec_start or ec_start < datetime.now(tz=pytz.UTC)) and not (ec_start < datetime.now(tz=pytz.UTC) < ec_end):
            write_out(f"Found existing candidate to update: {ec.CandidateName}")
            write_out(f"Updating candidate {ec.CandidateName} with new information.")
            c.StartObservability = genUtils.timeToString(c.StartObservability, shh=True)
            c.EndObservability = genUtils.timeToString(c.EndObservability, shh=True)
        else:
            c.StartObservability = ec.StartObservability
            c.EndObservability = ec.EndObservability
            write_out(f"Existing candidate for {ec.CandidateName} had a sooner future transit (at {ec.StartObservability}) than any others found. Keeping that transit.")
        # we update the candidate either way, in case other fields have changed
        c.ID = ec.ID
        updateCandidate(c, dbConnection)
    write_out(f"Candidates from csvs successfully updated.")


def update_database(dbPath):
    write_out("Updating TESS targets")
    dirname = os.path.dirname(__file__)
    csv_names = [os.path.join(dirname, f) for f in [F for F in os.listdir(dirname) if F.endswith(".csv")]]
    if csv_names:
        dbConnection = CandidateDatabase(dbPath, "TESS Database Agent")
        write_out(f"{len(csv_names)} TESS CSV(s) found:")
        write_out(*csv_names)
        write_out("Updating TESS database.")
        try:
            csv_candidates = make_csv_candidates(csv_names)
        except Exception as e:
            write_out("Error making candidates from CSV. Aborting.")
            write_out("Error:", e)
            write_out("""
                The TESS module assumes csvs all have the following columns:
                'TOI': float, int, or string. can have multiple transits for the same planet in the same csv.
                'RA': deg, float
                'Dec': deg, float
                'NightOfTransit': string in format "YYYY-MM-DD"
                'pl_tranmid': JD, float, UTC
                'pl_ingress': JD, float, UTC
                'pl_egress': JD, float, UTC
                'pl_trandur': days, float
                'pl_orbper': days, float
                'Vmag': float
                'Jmag': float
                'TransitDepth(ppm)': float
                'Priority': int
            """)
            del dbConnection
            raise e  
        try:
            update_and_insert(csv_candidates, dbConnection)
        except Exception as e:
            del dbConnection
            raise e
        write_out("TESS database updated. All done!")
        del dbConnection # close to unlock db
    else:
        write_out("No TESS CSVs found.")


if __name__ == "__main__":
    update_database(sys.argv[1])
