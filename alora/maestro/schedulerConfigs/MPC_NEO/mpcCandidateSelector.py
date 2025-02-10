import asyncio, os, sys
import logging
from datetime import datetime as dt, timedelta
import astropy.units as u
from pytz import UTC

try:
    grandparentDir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir))
    sys.path.append(
        grandparentDir)
    from scheduleLib import genUtils
    from scheduleLib.candidateDatabase import CandidateDatabase
    from schedulerConfigs.MPC_NEO.mpcTargetSelectorCore import TargetSelector
    from mpcCandidateLogger import getVelocities
    sys.path.remove(grandparentDir)

except:
    from scheduleLib import genUtils
    from scheduleLib.candidateDatabase import CandidateDatabase
    from schedulerConfigs.MPC_NEO.mpcTargetSelectorCore import TargetSelector
    from .mpcCandidateLogger import getVelocities


# pull MPC NEO candidates that are not removed and have been added in the last [lookback] hours
# check if they have a removal reason. if they do, ignore them
# if they don't, do the selection process, marking rejected reason if they're not observable by TMO

async def selectTargets(logger, lookback, dbPath, mpcPriority):
    logger.info("--- Selecting ---")

    dbConnection = CandidateDatabase(dbPath, "MPC Selector")
    targetSelector = TargetSelector()

    # update only the newest incarnation of each candidate
    dbConnection.db_cursor.execute("""WITH RankedCandidates AS (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY CandidateName ORDER BY DateAdded DESC) AS rn
        FROM Candidates
    )
    SELECT *
    FROM RankedCandidates
    WHERE rn = 1 AND RemovedReason IS NULL AND CandidateType IS \"MPC NEO\";
        """)

    candidates = dbConnection.queryToCandidates(dbConnection.db_cursor.fetchall())


    if candidates is None:
        logger.info("Candidate Selector: Didn't find any targets in need of updating. All set!")
        del dbConnection  # explicitly deleting these to make sure they close nicely
        del targetSelector
        exit()
    else:
        logger.info("Finding observability and evaluating " + str(len(candidates)) + " objects.")

    designations = [candidate.CandidateName for candidate in candidates]
    candidateDict = dict(zip(designations, candidates))
    windows = await targetSelector.calculateObservability(list(set(designations)))
    candidatesWithWindows = []
    rejected = []  # we're going to later wipe the rejected status of all candidates that are not marked rejected this time around (in case they had been rejected in the past)
    for desig, window in windows.items():
        candidate = candidateDict[desig]
        if window:
            logger.debug("Found window for " + desig + "!")
            # print("Found window for " + desig + "!")
            if not (candidate.isAfterStart(dt.now(tz=UTC)) and not candidate.isAfterEnd(dt.now(tz=UTC))):  # we don't want to change the start time of the window after it has started, unless the whole window is over (we can't generate ephems for the past so we would artificially shorten the window each time we run)
                candidateDict[desig].StartObservability = window[0]
            candidateDict[desig].EndObservability = window[1]
            candidatesWithWindows.append(desig)
        else:
            if not (candidate.isAfterStart(dt.now(tz=UTC)) and not candidate.isAfterEnd(dt.now(tz=UTC))):  # if the canidate has a window and it's already opened, don't mark it
                candidateDict[desig].RejectedReason = "Observability"
                logger.debug("Got None window for " + desig + ". Rejected for Observability.")
                # print("Got None window for " + desig + ". Rejected for Observability.")
                rejected.append(desig)
            elif candidate.hasField("RejectedReason"):
                rejected.append(desig)  # we don't want to have the candidate's rejection status get wiped just because it's after the window has started

    logger.info("Rejecting targets")
    for desig, candidate in candidateDict.items():
        if not candidate.hasField("Priority"):
            candidate.Priority = mpcPriority
        if not candidate.hasField("RMSE_RA") or not candidate.hasField("RMSE_Dec"):
            logger.info("Retrying uncertainty on " + desig)
            # logger.error("Selector uncertainty retry fetch uncertainties")
            offsetDict = await targetSelector.friend.get_uncertainties([desig])
            uncertainties = offsetDict.get(desig)
            if uncertainties is not None:
                logger.info("Retry successful")
                candidateDict[desig].RMSE_RA, candidateDict[desig].RMSE_Dec = uncertainties.RMSE_RA, uncertainties.RMSE_Dec
                candidateDict[desig].ApproachColor = uncertainties.color
            else:
                logger.warning("Uncertainty query for " + desig + " came back empty again.")
                logger.debug("Rejected " + desig + " for incomplete information.")
                candidateDict[desig].RejectedReason = "Incomplete uncertainty"
                rejected.append(desig)
                continue
        
        if (not candidate.hasField("dRA")) or (not candidate.hasField("dDec")):
            logger.info("Retrying velocity on " + desig)
            dRA, dDec = await getVelocities(candidate.CandidateName, targetSelector.mpc, logger, targetSelector)
            if dRA is not None and dDec is not None:
                logger.info("Retry successful")
                candidate.dRA, candidate.dDec = dRA*u.arcsec/u.minute, dDec*u.arcsec/u.minute
                # candidate.set_field("dRA",dRA)
                # candidate.set_field("dDec",dDec)
            else:
                logger.warning("Velocity query for " + desig + " came back empty again.")
                logger.debug("Rejected " + desig + " for incomplete information.")
                candidateDict[desig].RejectedReason = "Incomplete velocity"
                rejected.append(desig)
                continue

        if float(candidate.Magnitude) > targetSelector.vMagMax:
            candidateDict[desig].RejectedReason = "vMag"
            rejected.append(desig)
            logger.debug("Rejected " + desig + " for magnitude limit.")
            continue

        dDec_lims = targetSelector.dDec_limits
        dRA_lims = targetSelector.dRA_limits
        if candidate.dRA is None or candidate.dDec is None:
            logger.warning("No velocity data for " + desig)
        if not (dDec_lims[0] < abs(candidate.dDec.to_value("arcsec/minute")) < dDec_lims[1] or dRA_lims[0] < abs(candidate.dRA.to_value("arcsec/minute")) < dRA_lims[1]):
            rejected.append(desig)
            candidateDict[desig].RejectedReason = "dRA/dDec"
            logger.debug("Rejected " + desig + " for dRA/dDec.")
            continue

        if float(candidate.RMSE_RA) > targetSelector.raMaxRMSE or float(candidate.RMSE_Dec) > targetSelector.decMaxRMSE:
            rejected.append(desig)
            candidateDict[desig].RejectedReason = "RMSE"
            logger.debug("Rejected " + desig + " for error limit.")
            continue

    for desig in candidatesWithWindows:  # if the candidates were rejected before but aren't rejected this time through, we assume something has changed and they are now viable, so we remove their rejected reason
        candidate = candidateDict[desig]
        if desig not in rejected and candidate.hasField("RejectedReason"):
            delattr(candidate, "RejectedReason")
            dbConnection.setFieldNullByID(candidate.ID, "RejectedReason")
    logger.info("Updating database")
    for desig, candidate in candidateDict.items():
        dbConnection.editCandidateByID(candidate.ID, candidate.asDict())
        logger.debug("Updated " + desig + ".")
    del dbConnection


if __name__ == '__main__':
    # set up the logger
    logger = logging.getLogger(__name__)
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', filename='mpcCandidate.log', encoding='utf-8',
                        datefmt='%m/%d/%Y %H:%M:%S', level=logging.INFO)
    logger.addFilter(genUtils.filter)

    # run the program
    asyncio.run(selectTargets(logger, 24))
