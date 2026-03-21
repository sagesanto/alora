# Sage Santomenna 2023
# When run, attempts to import and run the database updater of each TypeConfig

import sys, os, math
from os.path import abspath, dirname, join, pardir

from alora.config.utils import Config
MODULE_PATH = abspath(join(dirname(__file__), pardir))

def PATH_TO(fname:str): return join(MODULE_PATH,fname)


sys.path.append(MODULE_PATH)
from alora.maestro.scheduleLib.crash_reports import run_with_crash_writing, write_crash_report


def main():
    try:
        import json
        import time
        from datetime import datetime, timedelta
        import pytz
        import concurrent.futures
        # from importlib import import_module

        from alora.maestro.scheduleLib import genUtils
        from alora.maestro.scheduleLib.genUtils import write_out
        from alora.maestro.scheduleLib.module_loader import ModuleManager

        logger = genUtils.configure_logger("DbUpdater")

        write_out("Starting DbUpdater.")

        manager = ModuleManager(write_out=write_out)
        modules = manager.load_active_modules()

        def generateNextRunTimestampString(delay):
            return (datetime.now() + timedelta(minutes=delay)).strftime("%m/%d %H:%M") + " local / " + (
                    datetime.now(pytz.UTC) + timedelta(minutes=delay)).strftime(
                "%m/%d %H:%M") + " UTC"

        maestro_settings = Config(join(MODULE_PATH,"files","configs","in_maestro_settings.toml"))
        waitTime = maestro_settings["databaseWaitTimeMinutes"]
        dbPath = maestro_settings["candidateDbPath"]
        do_autocycle = maestro_settings["do_database_autocycle"]
        
        def run_cycle():
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
            done_msg = f"DbUpdater: Finished:{run - errors}/{total} programs ran successfully."
            if do_autocycle:
                done_msg += f" Waiting until {generateNextRunTimestampString(waitTime)} for next cycle."
            write_out(done_msg)
            time.sleep(0.1)

        if do_autocycle:
            write_out("DbUpdater: Status:Cycling")
            run_cycle()
            next_run_time = datetime.now() + timedelta(minutes=waitTime)
        else:
            write_out("DbUpdater: Status: Autocycle disabled. Waiting for cycle start command from Maestro...")
        with concurrent.futures.ThreadPoolExecutor() as pool:
            futureStdInRead = pool.submit(genUtils.readStdin)
            while True:
                if do_autocycle and datetime.now() >= next_run_time:
                    write_out(f"DbUpdater: Status:Automatically starting next cycle because {waitTime} minutes have passed since the last cycle.")
                    run_cycle()
                    next_run_time = datetime.now() + timedelta(minutes=waitTime)
                if futureStdInRead.done():  # stdin got data
                    x = futureStdInRead.result()
                    print(f"DbUpdater: Got command from Maestro: '{x}'")
                    if x == "DbUpdater: Cycle\n":
                        write_out("DbUpdater: Status:Cycling")
                        run_cycle()
                        next_run_time = datetime.now() + timedelta(minutes=waitTime)
                    if x == "DbUpdater: Ping!\n":
                        write_out("DbUpdater: Pong!")
                    futureStdInRead = pool.submit(genUtils.readStdin)
                time.sleep(0.01)

    except Exception as e:
        sys.stderr.write("DbUpdater: Error: " + repr(e))
        raise e

if __name__ == '__main__':
    run_with_crash_writing("DbUpdater", main)