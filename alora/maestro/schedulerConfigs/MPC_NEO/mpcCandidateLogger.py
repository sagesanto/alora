import asyncio, os, sys
import logging
from datetime import datetime as dt, timedelta
import pytz
from colorlog import ColoredFormatter
from photometrics.mpc_neo_confirm import MPCNeoConfirm as mpcObj

try:
    grandparentDir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir))
    sys.path.append(
        grandparentDir)
    from scheduleLib import genUtils
    from scheduleLib.candidateDatabase import CandidateDatabase, Candidate
    from schedulerConfigs.MPC_NEO.mpcTargetSelectorCore import TargetSelector
    from schedulerConfigs.MPC_NEO import mpcUtils

    sys.path.remove(grandparentDir)
except:
    from scheduleLib import genUtils
    from scheduleLib.candidateDatabase import CandidateDatabase, Candidate
    from schedulerConfigs.MPC_NEO.mpcTargetSelectorCore import TargetSelector
    from schedulerConfigs.MPC_NEO import mpcUtils


async def getVelocities(desig, mpc, logger, targetSelector):  # get dRA and dDec
    now = dt.now(tz=pytz.UTC)
    try:
        # logger.error("get velocities calling asyncMultiEphem")
        ephems = await targetSelector.friend.get_ephems([desig], now, mpc, 500)
    except:
        logger.exception("Encountered exception while trying to get ephems for velocities for " + desig)
        return None, None
    if desig in ephems.keys() and ephems[desig]:
        eph = ephems[desig].get(now)
        return round(eph.dRA.to_value("arcsec/min"), 2), round(eph.dDec.to_value("arcsec/min"), 2)  # we want "/minute
    logger.info("Can't get velocity for " + desig + ": couldn't get ephemeris.")
    return None, None


async def listEntryToCandidate(entry, mpc, logger, targetSelector):
    constructDict = {}
    CandidateName = entry.designation
    CandidateType = "MPC NEO"
    constructDict["RA"], constructDict["Dec"] = entry.ra * 15, entry.dec
    constructDict["Magnitude"] = float(entry.vmag)
    expPair = mpcUtils._findExposure(constructDict["Magnitude"], str=False)
    constructDict["NumExposures"] = float(expPair[0])
    constructDict["ExposureTime"] = float(expPair[1])  # duration of observation, in seconds
    constructDict["Updated"] = genUtils.timeToString(mpcUtils.updatedStringToDatetime(entry.updated))
    dRA, dDec = await getVelocities(CandidateName, mpc, logger, targetSelector)
    # currently, can't get nObs and Score from mpc_neo_confirm. not going to implement it myself - we'll go without
    if dRA is not None and dDec is not None:
        constructDict["dRA"], constructDict["dDec"] = dRA, dDec
    else:
        logger.warning("Couldn't find velocities for " + CandidateName)

    constructDict["TransitTime"] = genUtils.timeToString(
        genUtils.roundToTenMinutes(
            genUtils.find_transit_time(genUtils.ensureAngle(str(constructDict["RA"]) + "h"), targetSelector.observatory)))
    return Candidate(CandidateName, CandidateType, **constructDict)


def candidateIsRemoved(candidate):
    return candidate.hasField("RemovedReason") and candidate.RemovedReason


def needsUpdate(listEntry, dbEntry):
    return genUtils.stringToTime(listEntry.Updated) > genUtils.stringToTime(dbEntry.Updated)


def updateCandidate(dbCandidate: Candidate, listCandidate: Candidate, dbConnection: CandidateDatabase):
    id = dbCandidate.ID
    dbConnection.editCandidateByID(id, listCandidate.asDict())


# this is where everything happens
async def runLogging(logger, lookback, candidateDbPath, mpcPriority):
    mpc = mpcObj()
    targetSelector = TargetSelector()
    dbConnection = CandidateDatabase(candidateDbPath, "MPCLogger")

    logger.info("--- Acquiring Candidates ---")
    currentCandidates = {}  # store desig:candidate for each candidate in the MPC's list of current candidates
    mpc.get_neo_list()  # prompt the mpc object to fetch the list
    for _ in range(3):
        # warm up the ol internet machine
        if mpc.neo_confirm_list is not None:
            break
        else:
            logger.error("Failed to get MPC list. Trying again.")
            mpc.get_neo_list()
    if mpc.neo_confirm_list is None:
        raise ConnectionError("Can't get list of candidates from MPC. Check internet connection")
    logger.info("Constructing Candidates from MPC List")
    cometList = await mpcUtils.getCometList(targetSelector.asyncHelper)
    for comet in cometList:
        logger.info(f"{comet} is a comet. Ignoring.")
    for entry in mpc.neo_confirm_list:  # access the list and create dict
        if entry.designation not in cometList:
            ent = await listEntryToCandidate(entry, mpc, logger, targetSelector)  # transform list entries to candidates
            currentCandidates[ent.CandidateName] = ent
    logger.info("Construction complete.")
    logger.info("Querying the MPC for uncertainties...")
    desigs = currentCandidates.keys()
    # logger.error("mpc logger fetch uncertainties")
    uncerts = await targetSelector.friend.get_uncertainties(desigs)
    for desig in desigs:  # loop over the candidates and find their uncertainties, adding them to the candidate object
        uncert_obj = uncerts.get(desig)
        if uncert_obj is not None:
            currentCandidates[desig].RMSE_RA, currentCandidates[desig].RMSE_Dec = uncert_obj.RMSE_RA, uncert_obj.RMSE_Dec
            currentCandidates[desig].ApproachColor = uncert_obj.color
        else:
            logger.warning("Uncertainty query for " + desig + " came back empty.")
    logger.info("Queried.")
    static = []
    updated = []  # candidates that appear in both the list and the database and may need to be updated
    new = []  # candidates that appear in the list but not in the database
    removed = []  # candidates that appear in the database but not in the list
    dbCandidates = dbConnection.table_query("Candidates", "*",
                                            "RemovedReason IS NULL AND CandidateType IS \"MPC NEO\"",
                                            [], returnAsCandidates=True)

    if dbCandidates:
        for c in dbCandidates:
            if c.CandidateType != "MPC NEO":
                print(f"UH OH! Candidate {c.CandidateName} is not an MPC target but we selected it anyway!")
        dbCandidates = {a.CandidateName: a for a in dbCandidates}
        for desig, candidate in currentCandidates.items():
            if desig in dbCandidates.keys():
                if candidateIsRemoved(dbCandidates[desig]):
                    logger.warning(
                        "That's odd. Candidate " + desig + " found in MPC table but marked as removed in database. Skipping and moving on.")
                    static.append(candidate)
                    continue
                # logger.debug("Checking for updates to" + desig)
                # if needsUpdate(candidate, dbCandidates[desig]):
                logger.info("Updating " + desig)
                candidate.Filter = "CLEAR"
                updateCandidate(dbCandidates[desig], candidate, dbConnection)
                updated.append(candidate)
                # else:
                #     static.append(candidate)
                #     logger.debug("None found")
                #     continue
            else:
                new.append(candidate)
                continue

        for candidate in dbCandidates.values():
            if candidate.CandidateName not in currentCandidates.keys():
                logger.info(
                    "Candidate " + candidate.CandidateName + " is in the database but not in the MPC table. Marking as removed.")
                dbConnection.removeCandidateByName(candidate.CandidateName, "Target removed from MPC list")
                removed.append(candidate)
    else:
        logger.info(
            "No candidates added in the last " + str(lookback) + " hours. Adding all targets in list.")
        new = list(currentCandidates.values())

    for candidate in new:  # add these
        candidate.Priority = mpcPriority
        newID = dbConnection.insertCandidate(candidate)
        logger.debug(
            "Created " + candidate.CandidateName + " with ID " + str(newID) + ".")

    logger.info("-Assessed Candidates")
    logger.info("New (" + str(len(new)) + ")")
    logger.debug(str(new))
    logger.info("Static (" + str(len(static)) + ")")
    logger.debug(str(static))
    logger.info("Updated (" + str(len(updated)) + ")")
    logger.debug(str(updated))
    logger.info("Removed (" + str(len(removed)) + ")")
    logger.debug(str(removed))

    # generalUtils.logAndPrint("Done. will run again at "+dbConnection.timeToString(dt.now()+timedelta(minutes=interval))+" PST.",logger.info)
    # print("\n")
    del dbConnection  # close the connection to unlock db


if __name__ == "__main__":
    LOGFORMAT = " %(asctime)s %(log_color)s%(levelname)-8s%(reset)s | %(log_color)s%(message)s%(reset)s"
    formatter = ColoredFormatter(LOGFORMAT)
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    stream.setLevel(logging.INFO)
    logger = logging.getLogger(__name__)
    logging.getLogger('').addHandler(stream)
    logging.basicConfig(filename='mpcCandidate.log', encoding='utf-8',
                        datefmt='%m/%d/%Y %H:%M:%S', level=logging.DEBUG)
    logging.getLogger('').addFilter(genUtils.filter)
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(runLogging(logger, 24))
