import traceback, sys, os
import datetime, pytz
import configparser
from os.path import join, exists
import tomlkit
dirname = os.path.abspath(join(os.path.dirname(__file__),os.pardir))
with open(join(dirname, 'files','configs','config.toml'),"rb") as f:
    config = tomlkit.load(f)

BASE_CRASH_DIR = join(dirname,config['BASE_CRASH_DIR'])

from alora.maestro.scheduleLib.genUtils import write_out

def write_crash_report(report_dir,e,tb=None):
    report_dir = join(BASE_CRASH_DIR, report_dir)
    os.makedirs(report_dir,exist_ok=True)
    timestamp = datetime.datetime.now(tz=pytz.UTC).strftime('%Y_%m_%d_%H_%M_%S')
    fname = join(report_dir, f'{timestamp}.txt')
    write_out(f"CRASH! Writing crash report to {fname}")
    
    with open(fname, 'w') as f:
        f.write("Crash report: \n")
        f.write('Exception: ' + str(e) + '\n')
        f.write('Traceback: ' + '\n')
        if tb:
            traceback.print_tb(tb, file=f)
        else:
            traceback.print_tb(sys.exc_info()[2], file=f)

def run_with_crash_writing(report_dir, function, *args, **kwargs):
    try:
        function(*args, **kwargs)
    except Exception as e:
        write_crash_report(report_dir, e)
        raise e
    except SystemExit as e:
        print("Recieved system exit, exiting...")
        print("Exit code or exception:", str(e))
        return
    except:
        write_crash_report(report_dir, "Unknown error")
        raise Exception("Unknown error")