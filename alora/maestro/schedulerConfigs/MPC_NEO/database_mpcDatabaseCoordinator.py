import asyncio
import logging
import sys, os, atexit
from os.path import join, dirname
import time
from datetime import datetime as dt, timedelta

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from colorlog import ColoredFormatter

try:
    from .mpcCandidateLogger import runLogging
    from .mpcCandidateSelector import selectTargets
except ImportError:
    from mpcCandidateLogger import runLogging
    from mpcCandidateSelector import selectTargets

try:
    grandparentDir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir))
    sys.path.append(grandparentDir)
    from scheduleLib import genUtils

    sys.path.remove(grandparentDir)

except ImportError:
    from scheduleLib import genUtils

mConfig = genUtils.Config(join(dirname(__file__),"config.toml"))


async def main(dbPath):
    MPC_PRIORITY = mConfig["priority"]
    lookback = mConfig["lookback"]

    dateFormat = '%m/%d/%Y %H:%M:%S'
    # LOGFORMAT = " %(asctime)s %(log_color)s%(levelname)-2s%(reset)s | %(log_color)s%(message)s%(reset)s"
    # colorFormatter = ColoredFormatter(LOGFORMAT, datefmt=dateFormat)
    # stream = logging.StreamHandler()
    # stream.setFormatter(colorFormatter)
    # stream.setLevel(logging.INFO if len(sys.argv) == 1 else logging.ERROR)
    # fileFormatter = logging.Formatter(fmt='%(asctime)s %(levelname)-2s | %(message)s', datefmt=dateFormat)
    # fileHandler = logging.FileHandler("mpcCandidate.log")
    # fileHandler.setFormatter(fileFormatter)
    # fileHandler.setLevel(logging.DEBUG)
    # logger = logging.getLogger(__name__)
    # logger.addHandler(fileHandler)
    # logger.addHandler(stream)
    # logger.setLevel(logging.DEBUG)
    # logger.addFilter(genUtils.filter)

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logger.addFilter(genUtils.filter)
    logger.info("---Starting cycle at " + dt.now().strftime(dateFormat) + " PST")

    coro = asyncio.wait_for(runLogging(logger, lookback, dbPath, MPC_PRIORITY),timeout=600)
    await coro
    logger.info("---Finished MPC logging without error at " + dt.now().strftime(dateFormat) + " PST")
    
    coro = asyncio.wait_for(selectTargets(logger, lookback, dbPath, MPC_PRIORITY),timeout=600)
    await coro
    logger.info("---Finished MPC selection without error at " + dt.now().strftime(dateFormat) + " PST")


    logger.info("---Done---")

def update_database(dbPath):
    asyncio.run(main(dbPath))

if __name__ == "__main__":
    logger = genUtils.configure_logger("mpcDatabaseCoordinator")
    update_database(dbPath=sys.argv[1])