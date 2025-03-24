# Sage Santomenna 2023
# Attempts to run and save requested ephemerides for Candidates by distributing them to their respective Config's
# ephemerides_[config_name].py files

import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir)))
from scheduleLib.crash_reports import run_with_crash_writing

from alora.config.utils import Config
from os.path import join, pardir, dirname, abspath
MODULE_PATH = abspath(join(dirname(__file__), pardir))

def main():
    import json
    import subprocess
    # from importlib import import_module

    from scheduleLib.genUtils import write_out
    from scheduleLib.module_loader import ModuleManager
    manager = ModuleManager(write_out=write_out)
    modules = manager.load_active_modules()

    targetsDict = json.loads(sys.argv[1])
    maestro_settings = Config(join(MODULE_PATH,"files","configs","in_maestro_settings.toml"))

    total = sum(len(value) for value in targetsDict.values())
    fetched = 0
    tasks = []

    # remove the previous versions of these ephems
    for desigs in targetsDict.values():
        for desig in desigs:
            try:
                # write_out(desig+".txt")
                os.remove(join(maestro_settings["ephemsSavePath"], desig+".txt"))
            except:
                pass
    #get the starting length to monitor progress
    startLen = len(os.listdir(maestro_settings["ephemsSavePath"]))
    for key in targetsDict.keys():
        if key in modules.keys():
            desigs = targetsDict[key]
            module = modules[key]
            module.get_ephems(json.dumps(desigs))
            fetched += len(os.listdir(maestro_settings["ephemsSavePath"])) - startLen
            write_out(" ".join(["Ephemeris: completed", str(fetched), "out of", str(total)]))
        else:
            write_out("No configured ephemerides file for " + key)

    write_out("Done fetching ephems.")

if __name__ == "__main__":
    run_with_crash_writing("ephemerides", main)
