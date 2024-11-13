# Sage Santomenna 2023
# While this process is running, it will listen for new jobs to perform on the database.
# Jobs can be sent through stdin as a jdumped dict of {"jobType":str,"arguments":list,"retries": int}
#      jobType: one of the types appearing in the keys of 'typeJobDict'
#      arguments: list of arguments to be passed to the job function
#      retries: number of times to retry job if it fails. if 0, job runs once

import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir)))
from scheduleLib.crash_reports import run_with_crash_writing

def main():
    import concurrent.futures
    import re, json, time
    import sqlite3

    from scheduleLib.candidateDatabase import Candidate, CandidateDatabase
    from scheduleLib import genUtils
    from scheduleLib.genUtils import write_out


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
    # arg: settings dict as jstr
    settings = json.loads(sys.argv[1])

    # this is where all the jobs are hooked up - job type (str) : function to perform
    typeJobDict = {"No Jobs": lambda: None, "remove": markCandidatesRemoved,
                "reject": markCandidatesRejected, "unreject": unrejectCandidates,
                "unremove": unremoveCandidates, "csvAdd": addCandidatesFromCsv, "jsonAdd": addCandidatesFromJson}

    currentJobType = "No Jobs"
    jobIDs = dict(zip(list(typeJobDict.keys()), [0] * len(typeJobDict)))
    waitingJobs = []
    completedJobs = []
    failedJobs = []

    candidateDb = CandidateDatabase(settings["candidateDbPath"], "MaestroUser")
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
                    statStr = json.dumps(
                        {"Current": currentJobType + "_" + str(jobIDs[currentJobType]), "Completed": completedJobs,
                        "Failed": failedJobs})
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
                        continue
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
                res = typeJobDict[currentJobType](*job["arguments"])
                if not res:  # 0 is good exit, otherwise can exit with failure message
                    completedJobs.append(job)
                    waitingJobs.remove(job)
                    write_out("DbOps: Status:Completed job \'{}_{}\'".format(currentJobType, str(jobIDs[currentJobType])))
                    continue
            except sqlite3.DatabaseError:  # db may be locked, no need to abort
                write_out("DbOps: Status:Retrying job after exception:", res)
                res = repr(e)
            except Exception as e:  # some other error. abort
                res = repr(e)
                write_out("DbOps: Status:Fatal error encountered during job \'{}_{}\': {}".format(currentJobType, str(
                    jobIDs[currentJobType]), str(res)))
                job["retries"] = 0  # cheap

            if not job["retries"]:  # we failed and are out of retries
                failedJobs.append(job)
                waitingJobs.remove(job)
                write_out("DbOps: Status:Failed job \'{}_{}\': {}".format(currentJobType, str(jobIDs[currentJobType]),
                                                                    str(res)))
                continue
            job["retries"] -= 1  # decrement allowed retries and try again

if __name__ == "__main__":
    run_with_crash_writing("dbOps", main)