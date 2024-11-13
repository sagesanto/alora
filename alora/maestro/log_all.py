import os, sys
from obs_logger import ObsLogger
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("root_dir", help="absolute path to the root directory to search and log", default=os.getcwd())

args = parser.parse_args()
os.chdir(args.root_dir)

p = os.getcwd()

def can_cast_to_int(s):
    try:
        int(s)
        return True
    except ValueError:
        return False

def j(*args):
    return os.path.join(p,*args)

dirs = [d for d in os.listdir() if os.path.isdir(j(d))]
dirs = [d for d in dirs if d[0] != "." and d[0] != "_"]
dirs = [d for d in dirs if '_' not in d and len(d) == len('20240119')]
dirs = [d for d in dirs if can_cast_to_int(d) and int(d) > 20230614] # can only log for 20230614+ because that's when database records start


obs_logger = ObsLogger()

for d in dirs:
    print("Searching",d)
    try:
        obs_log_path = j(d,"obs.log")
        metadata_db_path = j(d,"Metadata.db")
        schedule_path = j(d,"Scheduler.txt")
        try:
            for path in [obs_log_path, metadata_db_path, schedule_path]:
                if not os.path.exists(path):
                    raise FileNotFoundError(f"Could not find {path}")
        except FileNotFoundError as e:
            print("Not all files found.")
            continue
        obs_logger.log_from_schedule(schedule_path, obs_log_path, metadata_db_path)
        print("Logged observations for",d)
        print()
    except Exception as e:
        raise e
        # print("Error logging observations for",d)
        # print(e)
        # continue
print("Done")