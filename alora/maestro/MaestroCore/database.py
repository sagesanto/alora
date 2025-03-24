# Sage Santomenna 2023
# When run, attempts to import and run the database updater of each TypeConfig

import sys, os, math
from os.path import abspath, dirname, join, pardir

from alora.config.utils import Config
MODULE_PATH = abspath(join(dirname(__file__), pardir))

def PATH_TO(fname:str): return join(MODULE_PATH,fname)


sys.path.append(MODULE_PATH)
from scheduleLib.crash_reports import run_with_crash_writing, write_crash_report

def main():
    try:
        import json
        import time
        from datetime import datetime, timedelta
        import pytz
        import concurrent.futures
        # from importlib import import_module

        from scheduleLib import genUtils
        from scheduleLib.genUtils import write_out as _write_out
        from scheduleLib.module_loader import ModuleManager

        logger = genUtils.configure_logger("DbUpdater")

        def write_out(*args):
            _write_out(*args)
            # logger.info(" ".join([str(a) for a in args]))
        write_out("Starting to update database.")

        manager = ModuleManager(write_out=_write_out)
        modules = manager.load_active_modules()

        def generateNextRunTimestampString(delay):
            return (datetime.now() + timedelta(minutes=delay)).strftime("%m/%d %H:%M") + " local / " + (
                    datetime.now(pytz.UTC) + timedelta(minutes=delay)).strftime(
                "%m/%d %H:%M") + " UTC"

        maestro_settings = Config(join(MODULE_PATH,"files","configs","in_maestro_settings.toml"))
        waitTime = maestro_settings["databaseWaitTimeMinutes"]
        dbPath = maestro_settings["candidateDbPath"]

        while True:
            total = len(modules.keys())
            run = 0
            errors = 0
            for name, module in modules.items():
                errorCode = 0
                errorMsg = ''
                run += 1
                write_out(f"DbUpdater: Status:Running program {run}/{total} ({name}).")
                try:
                    module.update_database(dbPath)
                except Exception as e:
                    write_out(f"DbUpdater: Error:DbUpdater failed on program {run}/{total} ({name}): '{e}'.")
                    write_crash_report(os.path.join("DbUpdater", name.replace(" ","_")), e)
                    errors += 1
                else:
                    write_out(f"DbUpdater: Result:DbUpdater successfully ran program {run}/{total} ({name}).")
            if errors == 0:
                write_out(f"DbUpdater: CLEAR_ERROR (clear any error status because all programs ran successfully)")
            time.sleep(0.1)
            write_out(f"DbUpdater: Finished:{run - errors}/{total} programs ran successfully. Waiting until {generateNextRunTimestampString(waitTime)}")
            time.sleep(0.1)

            with concurrent.futures.ThreadPoolExecutor() as pool:
                futureStdInRead = pool.submit(genUtils.readStdin)
                for i in range(math.ceil(waitTime * 60 / 0.01)):
                    if futureStdInRead.done():  # stdin got data
                        x = futureStdInRead.result()
                        if x == "DbUpdater: Cycle\n":
                            write_out("DbUpdater: Status:Cycling")
                            break
                        if x == "DbUpdater: Ping!\n":
                            write_out("DbUpdater: Pong!")
                        futureStdInRead = pool.submit(genUtils.readStdin)
                    time.sleep(0.01)

    except Exception as e:
        sys.stderr.write("DbUpdater: Error: " + repr(e))
        raise e

if __name__ == '__main__':
    run_with_crash_writing("DbUpdater", main)