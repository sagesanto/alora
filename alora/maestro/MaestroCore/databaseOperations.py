# Sage Santomenna 2023
# While this process is running, it will listen for new jobs to perform on the database.
# Jobs can be sent through stdin as a jdumped dict of {"jobType":str,"arguments":list,"retries": int}
#      jobType: one of the types appearing in the keys of 'typeJobDict'
#      arguments: list of arguments to be passed to the job function
#      retries: number of times to retry job if it fails. if 0, job runs once

import sys, os
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir)))
from alora.maestro.scheduleLib.crash_reports import run_with_crash_writing, write_crash_report
from alora.config.utils import Config
from os.path import join, pardir, dirname, abspath
MODULE_PATH = abspath(join(dirname(__file__), pardir))
from enum import Enum

class JobType(Enum):
    REMOVE = 'remove'
    REJECT = 'reject'
    UNREJECT = 'unreject'
    UNREMOVE = 'unremove'
    CSV_ADD = 'csvAdd'
    JSON_ADD = 'jsonAdd'
    WHITELIST = 'whitelist'
    DE_WHITELIST = 'de_whitelist'
    BLACKLIST = 'blacklist'
    DE_BLACKLIST = 'de_blacklist'


def main():
    import concurrent.futures
    import re, json, time
    import sqlite3

    from alora.maestro.scheduleLib.candidateDatabase import Candidate, CandidateDatabase
    from alora.maestro.scheduleLib import genUtils
    from alora.maestro.scheduleLib.genUtils import write_out


    def _addCandidates(candidates):
        for candidate in candidates:
            try:
                candidateDb.insertCandidate(candidate)
            except:
                time.sleep(0.1)  # in case the insert failed because db in use
                try:
                    candidateDb.insertCandidate(candidate)
                except Exception as e:
                    write_out("Couldn't insert candidate! Error: ", repr(e))
                    pass


    def addCandidatesFromCsv(csvPath):
        """Add candidates from csv. WARNING: not safe to retry on failure."""
        candidates = Candidate.fromCSV(csvPath)
        _addCandidates(candidates)


    def addCandidatesFromJson(candidateDictListJson):
        """Add candidates from a jsonified list of dictionaries that are valid inputs to Candidate.fromDictionary(). WARNING: not safe to retry on failure."""
        candidates = []
        dicts = json.loads(candidateDictListJson)
        for d in dicts:
            candidates.append(Candidate.fromDictionary(d))
        _addCandidates(candidates)


    def whitelist_candidates(candidateIDs):
        print("whitelisting the following:", candidateIDs)
        for ID in candidateIDs:
            candidateDb.add_to_whitelist(ID)
        return 0


    def de_whitelist_candidates(candidateIDs):
        for ID in candidateIDs:
            candidateDb.remove_from_whitelist(ID)
        return 0


    def blacklist_candidates(candidateIDs):
        for ID in candidateIDs:
            candidateDb.add_to_blacklist(ID)
        return 0


    def de_blacklist_candidates(candidateIDs):
        for ID in candidateIDs:
            candidateDb.remove_from_blacklist(ID)
        return 0
    

    def markCandidatesRemoved(candidateIDs):
        for ID in candidateIDs:
            candidateDb.removeCandidateByID(ID, reason="User manual removal")
        return 0


    def markCandidatesRejected(candidateIDs):
        for ID in candidateIDs:
            candidateDb.rejectCandidateByID(ID, reason="User manual rejection")
        return 0


    def unremoveCandidates(candidateIDs):
        for ID in candidateIDs:
            candidateDb.setFieldNullByID(ID, colName="RemovedReason")
            candidateDb.setFieldNullByID(ID, colName="RemovedDt")
        return 0


    def unrejectCandidates(candidateIDs):
        for ID in candidateIDs:
            candidateDb.setFieldNullByID(ID, colName="RejectedReason")
        return 0


    # on launch, connect to the candidate database, then wait for a job to come through stdin in the form of a properly-formatted json string
    write_out("Starting db ops")
    maestro_settings = Config(join(MODULE_PATH,"files","configs","in_maestro_settings.toml"))

    # this is where all the jobs are hooked up - job type (str) : function to perform
    typeJobDict = {"No Jobs": lambda: None, 
                    JobType.REMOVE.value: markCandidatesRemoved,
                    JobType.REJECT.value: markCandidatesRejected,
                    JobType.UNREJECT.value: unrejectCandidates,
                    JobType.UNREMOVE.value: unremoveCandidates,
                    JobType.CSV_ADD.value: addCandidatesFromCsv, 
                    JobType.JSON_ADD.value: addCandidatesFromJson,
                    JobType.WHITELIST.value: whitelist_candidates,
                    JobType.DE_WHITELIST.value: de_whitelist_candidates,
                    JobType.BLACKLIST.value: blacklist_candidates,
                    JobType.DE_BLACKLIST.value: de_blacklist_candidates
                }

    currentJobType = "No Jobs"
    jobIDs = dict(zip(list(typeJobDict.keys()), [0] * len(typeJobDict)))
    waitingJobs = []
    completedJobs = []
    failedJobs = []
    candidateDb = CandidateDatabase(maestro_settings["candidateDbPath"], "MaestroUser")
    with concurrent.futures.ThreadPoolExecutor() as pool:
        # watch for input
        futureStdInRead = pool.submit(genUtils.readStdin)
        while True:
            time.sleep(0.1)
            if futureStdInRead.done():  # stdin got data
                x = futureStdInRead.result()
                if x == "Kill\n":
                    write_out("DbOps: Status:Killing self")
                    candidateDb.close()
                    exit()
                if x == "DbOps: Ping!\n":
                    write_out("DbOps: Pong!")
                if x == "DbOps: Jobs\n":
                    statStr = json.dumps({
                        "Current": currentJobType + "_" + str(jobIDs[currentJobType]),
                        "Completed": completedJobs,
                        "Failed": failedJobs
                    })
                    write_out("Jobs:" + statStr)
                elif x.startswith("DbOps: NewJob"):
                    try:
                        jobDict = json.loads(x.replace("DbOps: NewJob:", "").replace("\n", ""))
                        tType, tArgs, tRetries = jobDict["jobType"], jobDict["arguments"], jobDict["retries"]
                        tFunc = typeJobDict[tType]
                    except Exception as e:
                        write_out("Badly formatted job: {}".format(str(job)))
                        write_out(repr(e))
                        failedJobs.append(job)
                    else:
                        jobIDs[tType] += 1
                        waitingJobs.append(jobDict)
                futureStdInRead = pool.submit(genUtils.readStdin)

            # handle jobs
            if not len(waitingJobs):
                currentJobType = "No Jobs"
                continue
            job = waitingJobs[0]
            currentJobType = job["jobType"]
            try:
                args = job["arguments"]
                # try: 
                #     [arg for arg in args]
                # except TypeError:
                #     args = [args]
                write_out("args:",args)
                write_out(type(args))
                res = typeJobDict[currentJobType](*args)
                if not res:  # 0 is good exit, otherwise can exit with failure message
                    completedJobs.append(job)
                    waitingJobs.remove(job)
                    write_out("DbOps: Result:Completed job \'{}_{}\'".format(currentJobType, str(jobIDs[currentJobType])))
                    continue
            except sqlite3.DatabaseError:  # db may be locked, no need to abort
                write_out("DbOps: Status:Retrying job after exception:", res)
                res = repr(e)
            except Exception as e:  # some other error. abort
                res = repr(e)
                write_crash_report("dbOps",e)
                write_out("DbOps: Error:Fatal error encountered during job \'{}_{}\': {}".format(currentJobType, str(
                    jobIDs[currentJobType]), str(res)))
                job["retries"] = 0  # cheap

            if not job["retries"]:  # we failed and are out of retries
                failedJobs.append(job)
                waitingJobs.remove(job)
                write_out("DbOps: Failed:Failed job \'{}_{}\': {}".format(currentJobType, str(jobIDs[currentJobType]),
                                                                    str(res)))
                continue
            job["retries"] -= 1  # decrement allowed retries and try again

if __name__ == "__main__":
    run_with_crash_writing("dbOps", main)