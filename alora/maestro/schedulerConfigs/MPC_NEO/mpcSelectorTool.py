#Sage Santomenna 2023

import argparse
import asyncio
import logging
import os
import shutil

from colorlog import ColoredFormatter
from httpx import RemoteProtocolError

from schedulerConfigs.MPC_NEO import mpcTargetSelectorCore as targetCore

#Sage Santomenna 2023

# --- set up logging ---
LOGFORMAT = "  %(log_color)s%(levelname)-8s%(reset)s | %(log_color)s%(message)s%(reset)s"
LOG_LEVEL = logging.ERROR
logging.root.setLevel(LOG_LEVEL)
formatter = ColoredFormatter(LOGFORMAT)
stream = logging.StreamHandler()
stream.setLevel(LOG_LEVEL)
stream.setFormatter(formatter)

# --- take command line arguments ---
parser = argparse.ArgumentParser(description='Fetch and downselect MPC targets')
parser.add_argument('csvOutputDir', type=str,
                    help='Path to output generated csvs. Will be created if does not exist')
parser.add_argument('ephemDir', type=str,
                    help='Path to output final ephemerides. Will be created if does not exist')
parser.add_argument('plotDir', nargs='?', default=None, help = "Optional: specify a location to save plots")

parser.add_argument('-o', '-overwrite', action='store_true', dest="overwrite", help='if the indicated output directories already exist, empty them before running')

args = parser.parse_args()

csvOutputDir = args.csvOutputDir
ephemDir = args.ephemDir
plotDir = args.plotDir

# --- prepare save dirs ---
for directory in [csvOutputDir, ephemDir,plotDir]:
    if not os.path.exists(directory):
        os.mkdir(directory)
    elif args.overwrite:
        shutil.rmtree(directory)
        os.mkdir(directory)


# --- prepare async event loop ---
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# --- initialize selector ---
targetFinder = targetCore.TargetSelector()
targetFinder.logger.addHandler(stream)
targetFinder.printSetupInfo()

# --- perform selection ---
targetFinder.makeMpcDataframe()

targetFinder.pruneMpcDf()

print("Fetching and (optionally) plotting uncertainties of the targets - this may take a while. . .")
loop.run_until_complete(targetFinder.getFilteredUncertainties(graph=True,savePath=plotDir))

print("\033[1;32mUncertainties retrieved:\033[0;0m")
print(targetFinder.filtDf.to_string())

targetFinder.pruneByError()

print("\033[1;32mHere are the targets that meet all criteria:\033[0;0m")
print(targetFinder.filtDf.to_string())

targetFinder.saveCSVs(csvOutputDir)

# --- save ---
print("Fetching and saving ephemeris for these targets. . .")
try:
    filteredEphems = loop.run_until_complete(targetFinder.fetchFilteredEphemerides())
    targetCore.saveEphemerides(filteredEphems, ephemDir)
    print("Fetched. Find them in",ephemDir)
except RemoteProtocolError as e:
    print("\033[1;33m"+"Encountered fatal server error while fetching ephemeris. Error is as follows:\033[0;0m")
    print(repr(e))
    raise e

# --- clean up ---
targetFinder.killClients()
