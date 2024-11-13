import traceback, sys, os
import datetime, pytz
import configparser

dirname = os.path.abspath(os.path.join(os.path.dirname(__file__),os.pardir))
config = configparser.ConfigParser()
config.read(os.path.join(dirname, 'files','configs','config.txt'))
config = config['DEFAULT']

BASE_CRASH_DIR = config['BASE_CRASH_DIR'] 

from .genUtils import write_out

def write_crash_report(report_dir,e,tb=None):
    report_dir = os.path.join(BASE_CRASH_DIR, report_dir)
    if not os.path.exists(report_dir):
        os.makedirs(report_dir)
    timestamp = datetime.datetime.now(tz=pytz.UTC).strftime('%Y_%m_%d_%H_%M_%S')
    fname = os.path.join(report_dir, f'{timestamp}.txt')
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