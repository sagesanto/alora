import asyncio
import json
import logging
import os
import sys, time, pytz
from .mpcUtils import asyncMultiEphem, UncertainEphemFriend
from photometrics.mpc_neo_confirm import MPCNeoConfirm
from datetime import datetime, timedelta
import traceback
import configparser

# try:
#     grandparentDir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir))
#     sys.path.append(grandparentDir)
#     from alora.maestro.scheduleLib.asyncUtils import AsyncHelper
#     sys.path.remove(grandparentDir)
# except:
#     from alora.maestro.scheduleLib.asyncUtils import AsyncHelper

def get_ephems(desigs, settings):
    # aConfig = configparser.ConfigParser()
    # aConfig.read(os.path.join(os.path.dirname(__file__),os.pardir,os.pardir,"files", "configs", "async_config.txt"))
    # aConfig = aConfig["DEFAULT"]

    # HEAVY_LOGGING = aConfig.getboolean("HEAVY_LOGGING")
    # MAX_SIMULTANEOUS_REQUESTS = aConfig.getint("MAX_SIMULTANEOUS_REQUESTS")
    # ASYNC_REQUEST_DELAY_S = aConfig.getfloat("ASYNC_REQUEST_DELAY_S")
    
    logger=logging.getLogger("__name__")

    friend = UncertainEphemFriend()

    try:
        # desigs, settings = sys.argv[1:3]
        desigs, settings = json.loads(desigs), json.loads(settings)
        intervalDict = {0: 3, 1: 2, 2: 1, 3: 0}
        mpcInst = MPCNeoConfirm()
        interval = intervalDict[settings["ephemInterval"]]  # this maps ephem interval number from settings (which is the index of the dropdown the user uses) to the mpc's numbering system
        mpcInst.int = interval
        # asyncInst = AsyncHelper(True, max_simultaneous_requests=MAX_SIMULTANEOUS_REQUESTS, time_between_batches=ASYNC_REQUEST_DELAY_S, do_heavy_logging=HEAVY_LOGGING, timeout=int(settings["ephemTimeout"]))
        print()
        ephems = asyncio.run(friend.get_ephems(desigs, datetime.now(pytz.utc) + timedelta(hours=int(settings["ephemStartDelayHrs"])), mpcInst, obsCode=settings["ephemsObsCode"]))

        for desig, ephem in ephems.items():
            if ephem:
                ephem.write(settings["ephemsSavePath"], logger, filename=f"{desig}.txt", scheduler_format=settings["ephemFormat"] == 0, format_only=settings["ephemFormat"] == 0)
            else:
                sys.stderr.write("Failed to get ephems for target "+desig)
                sys.stderr.flush()


    except Exception as e:
        sys.stderr.write(repr(e))
        sys.stderr.write(traceback.format_exc())
        sys.stderr.flush()
