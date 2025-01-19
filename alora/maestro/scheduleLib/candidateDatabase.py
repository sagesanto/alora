# Sage Santomenna 2023
# definition of Candidate and CandidateDatabase classes
# Candidate - the common language of the program. stores information about the target and provides convenience functions
# CandidateDatabase - interface between the user and an existing candidate database, allowing Candidate storage, management, and queries

import os, json
import logging
import logging.config
import pandas as pd
import pytz
import sqlite3
from collections import OrderedDict
from datetime import datetime, timedelta
from string import Template
from astropy.coordinates import SkyCoord, Angle
from astropy import units as u

from alora.maestro.scheduleLib import genUtils
from alora.maestro.scheduleLib.sql_database import SQLDatabase

# try:
#     from scheduleLib import genUtils
#     from scheduleLib.sql_database import SQLDatabase
# except ImportError:
#     import genUtils
#     from sql_database import SQLDatabase

validFields = ["CandidateName", "CandidateType", "ID", "Author", "DateAdded", "DateLastEdited", "RemovedDt",
               "RemovedReason", "RejectedReason", 'Night',
               'Updated', 'StartObservability', 'EndObservability', 'TransitTime', 'RA', 'Dec', 'dRA', 'dDec',
               'Magnitude', 'RMSE_RA',
               'RMSE_Dec', "Score", "nObs", 'ApproachColor', 'NumExposures', 'ExposureTime', 'Scheduled', 'Observed',
               'Processed', 'Submitted', 'Notes', 'Priority', 'Filter', 'Guide',
               'CVal1', 'CVal2', 'CVal3', 'CVal4', 'CVal5', 'CVal6', 'CVal7', 'CVal8', 'CVal9', 'CVal10']

logger = logging.getLogger(__name__)
# MPC target's Name	Processed	Submitted	approx. transit time (@TMO)	RA	Dec	RA Vel ("/min)	Dec Vel ("/min)	Vmag	~Error (arcsec)	Error Color
# CandidateName, Processed, Submitted, TransitTime, RA, Dec, dRA, dDec, Magnitude, RMSE
def generateID(candidateName, candidateType, author):
    hashed = str(hash(candidateName + candidateType + author))
    return int(hashed)


# noinspection PyUnresolvedReferences
class Candidate:
    def __init__(self, CandidateName: str, CandidateType: str, **kwargs):
        """!
        Preferred construction method is via CandidateDatabase.queryToCandidates
        Candidates are key to the operation of basically everything else. Each Candidate represents one target and
        stores information about where it is, when it can be observed, how it should be scheduled, etc. Candidates
        are intended to work in conjunction with user-defined configuration modules that interface with the database,
        scheduler, etc to give functionality.
        RA Dec are, unforunately, provided as astropy Angles or DECIMAL HOURS
        @param CandidateType: string. should exactly match the name of the module with which it should be associated
        @param kwargs: a whole litany of relevant information, some required for construction
        """
        self.CandidateName = CandidateName
        self.CandidateType = CandidateType
        for key, value in kwargs.items():
            if key in validFields:
                if key in ["RA","Dec"]:
                    if not isinstance(value, Angle):
                        value = Angle(float(value),unit="degree")
                self.__dict__[key] = value
            else:
                raise ValueError(
                    "Bad argument: " + key + " is not a valid argument for candidate construction. Valid arguments are " + str(
                        validFields))

    def __str__(self):
        return str(dict(self.__dict__))

    def __repr__(self):
        return "Candidate " + self.asDict()[
            "CandidateName"] + " (" + self.CandidateType + ")"  # can't print self.CandidateName directly for whatever reason

    def set_field(self, field, value):
        if field not in validFields:
            raise ValueError(
                "Bad argument: " + field + " is not a valid argument for candidate construction. Valid arguments are " + str(
                    validFields))
        self.__dict__[field] = value


    def asDict(self):
        d = self.__dict__.copy()
        RA = d.get("RA",None)
        dec = d.get("Dec", None)
        if RA is not None:
            d["RA"] = RA.degree
        if dec is not None:
            d["Dec"] = dec.degree
        return d

    def genGenericScheduleLine(self, filterName: str, startDt: datetime, name: str, description: str, exposureTime=None,
                               exposures=None, move=True, bin2fits=False,
                               guiding=True):
        """!
        Generate a generic schedule from this Candidate. See \ref genUtils.genericScheduleLine for full documentation
        @param exposureTime: exp time in seconds. if None, uses self.ExposureTime instead
        @type exposureTime: float|int|str|None
        @param exposures: number of expsosures. if None, uses self.NumExposures instead
        @type exposures: int|str|None
        @return: line to insert into schedule text file
        @rtype: str
        """

        exposureTime = exposureTime or self.ExposureTime
        exposures = exposures or self.NumExposures

        return genUtils.genericScheduleLine(self.RA, self.Dec, filterName, startDt, name, description, exposureTime,
                                            exposures, move, bin2fits, guiding)

    @classmethod
    def fromDictionary(cls, entry: dict):
        """!
        Convert a returned database entry to a Candidate object
        @param entry: a dictionary returned (inside a list) from a database query
        @return: Candidate object
        """
        CandidateName, CandidateType = entry.pop("CandidateName"), entry.pop("CandidateType")
        d = {}
        for key, value in entry.items():
            if key in validFields:
                d[key] = value
        try:
            return cls(CandidateName, CandidateType, **entry)  # splat
        except Exception as e:
            print(f"Error constructing candidate from dictionary {entry}: {e}")
            return

    @staticmethod
    def candidatesToDf(candidateList: list):
        if not len(candidateList):
            return None
        candidateDicts = [candidate.asDict() for candidate in candidateList]
        keys = list(OrderedDict.fromkeys(key for dictionary in candidateDicts.copy() for key in dictionary.keys()))
        seriesList = [pd.Series(d) for d in candidateDicts]
        df = pd.DataFrame(seriesList, columns=keys)
        return df

    @staticmethod
    def dfToCandidates(df):
        """!
        Turn a dataframe output by candidatesToDf back into Candidates
        """
        return [Candidate.fromDictionary(d) for d in df.to_dict(orient='records')]

    @staticmethod
    def fromCSV(path):
        df = pd.read_csv(path)
        return Candidate.dfToCandidates(df)

    def hasField(self, field):
        return field in self.__dict__.keys() and field # so that setting the RemovedReason of a candidate to '' means it is not removed

    def isAfterStart(self, dt: datetime):
        """!
        Is the provided time after the start time of this Candidate's observability window?
        @return: bool
        """
        dt = genUtils.stringToTime(dt)  # ensure that we have a datetime object
        if self.hasField("StartObservability"):
            # NOTE: changed > to >= on 1/2/24
            if dt >= genUtils.stringToTime(self.StartObservability):
                return True
        return False

    def isValid(self):
        return not self.hasField("RemovedReason") and not self.hasField("RejectedReason")

    def isAfterEnd(self, dt: datetime):
        """!
        Is the provided time after the end time of this Candidate's observability window?
        @return: bool
        """
        if self.hasField("EndObservability"):
            if dt > genUtils.stringToTime(self.EndObservability):
                return True
        return False

    def evaluateStaticObservability(self, start, end, minHoursVisible, locationInfo):
        """!
        TMO-specific helper function to determine the visibility of a fixed Candidate
        """

        siderealDay = timedelta(hours=23, minutes=56, seconds=4.091)  # sue me
        window = genUtils.static_observability_window(self.RA, self.Dec)
        if window[0] and window[1]:
            # if the whole window is behind us, shift it forward one sidereal day. cheap trick
            if window[1] < datetime.now(tz=pytz.UTC):
                window[0] += siderealDay
                window[1] += siderealDay
            self.StartObservability, self.EndObservability = [genUtils.timeToString(a) for a in window]
        else:
            self.RejectedReason = "Observability"
        if not self.isObservableBetween(start, end, minHoursVisible):
            # print(self.CandidateName,"is observable between", self.StartObservability, "and", self.EndObservability, "but not between", start, "and", end )
            self.RejectedReason = "Observability"
        return self

    def windowViable(self, start, end):
        """!
        Is the candidate observable for the entirety of the time between start and end, inclusive
        """
        return self.isAfterStart(start) and not self.isAfterEnd(end)
    

    def isObservableBetween(self, start, end, duration):
        """!
        Is this Candidate observable between `start` and `end` for at least `duration` hours?
        @param start: datetime or valid string
        @param end: datetime or valid string
        @param duration: hours, float
        @return: bool
        """
        start, end = genUtils.stringToTime(start).replace(tzinfo=pytz.UTC), genUtils.stringToTime(
            end).replace(tzinfo=pytz.UTC)  # ensure we have datetime object

        if self.hasField("StartObservability") and self.hasField("EndObservability"):
            startObs = genUtils.stringToTime(self.StartObservability).replace(tzinfo=pytz.UTC)
            endObs = genUtils.stringToTime(self.EndObservability).replace(tzinfo=pytz.UTC)
            # print(start, end)
            # print(startObs, endObs)
            if start < endObs <= end or start < startObs <= end:  # the windows do overlap
                # print("Max (start):", max(start, startObs))
                # print("Min (end):", min(end, endObs))
                dur = min(end, endObs) - max(start, startObs)
                # print("difference", dur)
                if dur >= timedelta(hours=duration):  # the window is longer than min allowed duration
                    return True, dur
            elif startObs < start and endObs >= end:
                # print("spanning case: {} observable between {} and {}".format(self.CandidateName,self.StartObservability,self.EndObservability))
                dur = end - start
                # print("difference", dur)
                if dur >= timedelta(hours=duration):  # the window is longer than min allowed duration
                    return True, dur
            return False


class CandidateDatabase(SQLDatabase):
    def __init__(self, dbPath, author):
        super().__init__()
        self.logger = logger
        self.db_path = dbPath
        self.__author = author
        self.open(dbPath)
        if self.isConnected:
            self.logger.info("Connection confirmed")
        else:
            raise sqlite3.DatabaseError("Connection to candidate database failed")
        self.__existingIDs = []  # get and store a list of existing IDs. risk of collision low, so I'm not too worried about not calling this before making ids

    def __del__(self):
        try:
            self._releaseDatabase()  # commit anything that might be left if we crash
        except:
            pass
        self.close()

    @staticmethod
    def timestamp():
        # UTC time in YYYY-MM-DD HH:MM:SS format
        return genUtils.timeToString(datetime.utcnow())

    @staticmethod
    def query_result_to_dict(queryResults):
        """!
        Convert SQLite query results to a list of dictionaries.
        @param queryResults: List of SQLite query row objects.
        @return: List of dictionaries representing query results.
        """
        # dictionaries = []
        # for row in queryResults:
        #     if row:
        #         print(row)
        #         print(dict(row))
        #         dictionaries.append(dict(row))

        dictionaries = [dict(row) for row in queryResults if row]
        return [{k: v for k, v in a.items() if v is not None} for a in dictionaries if a]

    def queryToCandidates(self, queryResults):
        # try:
        dicts = CandidateDatabase.query_result_to_dict(queryResults)
        dicts = [self.removeInvalidFields(d, allowProtected=True) for d in dicts]
        return [Candidate.fromDictionary(d) for d in dicts]

    def open(self, db_file, timeout=5, check_same_thread=False):
        """!
        Establish connection to the candidate database
        @param db_file: Path to the candidate database SHOULD MAKE THIS INTERNAL
        @param check_same_thread: Check if the database should be read by only one thread
        """
        if not os.path.isfile(db_file):
            self.logger.error('Database file %s not found.' % db_file)
            raise ValueError("Database file not found")
        try:
            super().open(db_file, timeout=timeout, check_same_thread=check_same_thread,
                                                 detect_types=sqlite3.PARSE_DECLTYPES |
                                                              sqlite3.PARSE_COLNAMES)
        except Exception as err:
            self.logger.error('Unable to open sqlite database %s' % db_file)
            self.logger.error('sqlite error : %s' % err)
            raise err
        else:
            self._db_name = os.path.splitext(db_file)[0]
            self.db_cursor.execute('pragma busy_timeout=2000')  # try write commands with a 2-second busy timeout
            self.logger.info("Connected to candidate database")
        return

    def table_query(self, table_name, columns, condition, values, returnAsCandidates=False, unique=False):
        """!Query table based on condition. If no condition given, will return the whole table - if this isn't what you want, be careful!
        Parameters
        ----------
        table_name : str
            Database table name
        columns : str
            table columns to query
        condition : str
            sql conditional statement
        values : list or tuple
            List of values corresponding to conditional statement
        returnAsCandidates: bool
            Results
        Return
        ------
        rows : dict or list
            Python list of dicts, indexed by column name, or list of Candidate objects
        """
        result = self.query_result_to_dict(super().table_query(table_name, columns, condition, values))
        if result:
            self.logger.debug("Query: Retrieved " + str(len(result)) + " record(s) for candidates in response to query")
            if returnAsCandidates:
                result = [Candidate.fromDictionary(row) for row in result]
                result = [c for c in result if c]
            return result
        return None

    def insertCandidate(self, candidate: Candidate):
        candidate = candidate.asDict()
        candidate["Author"] = self.__author
        candidate["DateAdded"] = CandidateDatabase.timestamp()
        id = generateID(candidate["CandidateName"], candidate["CandidateType"], self.__author)
        candidate["ID"] = id
        try:
            self.insert_records("Candidates", candidate)
        except Exception as e:
            self.logger.error("Can't insert " + str(candidate) + ". PBCAK Error")
            self.logger.error(repr(e))
            raise e
        self.logger.info(
            "Inserted " + candidate["CandidateType"] + " candidate \'" + candidate["CandidateName"] + "\' from " +
            candidate["Author"])
        return id

    def fetchIDs(self):
        self.__existingIDs = [row["ID"] for row in self.table_query("Candidates", "ID", '', []) if row]

    def isFieldProtected(self, field):
        return field in ["Author", "DateAdded", "ID"]

    def removeInvalidFields(self, dictionary, allowProtected=False):
        badKeys = []
        for key, value in dictionary.items():
            if key not in validFields or (self.isFieldProtected(key) and (not allowProtected)):
                badKeys.append(key)
        for key in badKeys:
            dictionary.pop(key)
        return dictionary

    def candidatesForTimeRange(self, obsStart, obsEnd, duration, candidate_type=None):
        if candidate_type is None:
            candidates = self.table_query("Candidates", "*",
                                      "RemovedReason IS NULL AND RejectedReason IS NULL", [], returnAsCandidates=True)
        else:
            candidates = self.table_query("Candidates", "*",
                                      "RemovedReason IS NULL AND RejectedReason IS NULL AND CandidateType IS ?", [candidate_type], returnAsCandidates=True)

        if candidates is None:
            return []
        res = [candidate for candidate in candidates if candidate.isObservableBetween(obsStart, obsEnd, duration)]
        candidateDict = {}
        for c in res:
            if c.CandidateName not in candidateDict.keys():
                candidateDict[c.CandidateName] = c
            else:
                duplicate = candidateDict[c.CandidateName]
                if genUtils.stringToTime(duplicate.Updated) < genUtils.stringToTime(c.Updated):
                    candidateDict[c.CandidateName] = c
        res = list(candidateDict.values())
        return res

    # def candidates

    def candidatesAddedSince(self, when):
        """!
        Query the database for candidates added since 'when'
        @param when: datetime or string, PST
        @return: A list of Candidates, each constructed from a row in the dataframe, or None
        """
        when = genUtils.timeToString(when)
        if when is None:
            return None
        queryResult = self.table_query("Candidates", "*", "DateAdded > ?", [when], returnAsCandidates=True)
        if queryResult:
            return queryResult
        else:
            self.logger.warning("Received empty query result for candidates added since " + when)
            return None

    def getCandidateByID(self, ID: int):
        """
        Get a candidate by its ID. Returns a Candidate object or None
        @param ID: the candidate ID
        @type ID: int
        @return: list of Candidate objects, or None
        @rtype: list[Candidate]|None
        """
        return self.table_query("Candidates", "*", "ID = ?", [ID], returnAsCandidates=True)

    def getCandidatesByIDs(self, IDList):
        """
        Get a list of candidates by their IDs. Returns a list of Candidate objects or None
        @param IDList: list of candidate IDs
        @type IDList: list
        @return: list of Candidate objects or None
        @rtype: list[Candidate] | None
        """
        return self.table_query("Candidates", "*", "ID IN (" + ",".join(["?" for _ in IDList]) + ")",IDList,returnAsCandidates=True)

    def getCandidateByName(self, name):
        """
        Get candidate(s) that match the provided name. Returns a list of Candidate objects or None
        @param name: the candidate name
        @type name: str
        @return: list of Candidate objects or None
        @rtype: list[Candidate]|None
        """
        return self.table_query("Candidates", "*", "CandidateName = ?", [name], returnAsCandidates=True)

    def getCandidatesByNames(self, nameList):
        """
        Get candidate(s) that match the one of the provided names. Returns a list of Candidate objects or None
        @param nameList: list of candidate names
        @type nameList: list
        @return: list of Candidate objects or None
        @rtype: list[Candidate]|None
        """
        return self.table_query("Candidates", "*", "CandidateName IN (" + ",".join(["?" for _ in nameList]) + ")",nameList + ")", returnAsCandidates=True)
    
    def getCandidatesByType(self, candidateType):
        """
        Get candidate(s) that match the provided type. Returns a list of Candidate objects or None
        @param candidateType: the candidate type
        @type candidateType: str
        @return: list of Candidate objects or None
        @rtype: list[Candidate]|None
        """
        return self.table_query("Candidates", "*", "CandidateType = ?", [candidateType], returnAsCandidates=True)

    def editCandidateByID(self, ID, updateDict):
        """
        Update candidate with ID 'ID' in database so that fields in updateDict are updated to have the values in updateDict
        """
        updateDict = self.removeInvalidFields(updateDict)
        if len(updateDict):
            updateDict["DateLastEdited"] = CandidateDatabase.timestamp()
            self.table_update("Candidates", updateDict, "ID = " + str(ID))

    def _releaseDatabase(self):
        self.db_connection.commit()

    def setFieldNullByID(self, ID, colName):
        """
        Clear the value of a field to NULL in a candidate with ID 'ID'
        """
        sql_template = Template('UPDATE Candidates SET $column_name = ? WHERE \"ID\" = $id')
        sql_statement = sql_template.substitute({'column_name': colName, 'id': str(ID)})
        self.db_cursor.execute(sql_statement, [None])
        self.db_connection.commit()

    def clear_invalid_status(self,ID):
        self.setFieldNullByID(ID, "RemovedReason")
        self.setFieldNullByID(ID, "RejectedReason")


    def removeCandidateByName(self, candidateName, reason):
        """!
        Attempt to remove all candidates with the name candidateName,
        """
        self.db_cursor.execute("SELECT ID FROM Candidates WHERE CandidateName = ? AND RemovedReason IS NULL",
                               (candidateName,))
        IDres = CandidateDatabase.query_result_to_dict(self.db_cursor.fetchall())
        if IDres:
            for row in IDres:
                self.removeCandidateByID(row["ID"], reason)
            return

        print("Can't find any candidates with name {} to remove".format(candidateName))
        self.logger.warning("Can't find any candidates with name {} to remove".format(candidateName))

    def removeCandidateByID(self, ID: str, reason: str):
        """
        Mark a candidate as removed in the database. This is a soft delete, and the candidate will still be in the database (but will not be considered "valid" if checked). Sets the Removed, RemovedReason, and RemovedDt fields.
        """
        candidate = self.getCandidateByID(ID)[0]
        print("attempting to remove candidate with ID", ID)
        if candidate:
            reason = self.__author + ": " + reason
            updateDict = {"RemovedDt": CandidateDatabase.timestamp(), "RemovedReason": reason,
                          "DateLastEdited": CandidateDatabase.timestamp()}
            self.table_update("Candidates", updateDict, "ID = " + str(ID))
            self.logger.info("Removed candidate " + candidate.CandidateName + " for reason " + reason)
            print("Removed candidate " + candidate.CandidateName + " for reason " + reason)
            self.db_connection.commit()
        else:
            self.logger.error("Couldn't find target with ID " + ID + ". Can't update.")
            return None
        return ID

    def rejectCandidateByID(self, ID: str, reason: str):
        candidate = self.getCandidateByID(ID)[0]
        print("attempting to remove candidate with ID", ID)
        if candidate:
            reason = self.__author + ": " + reason
            updateDict = {"RejectedReason": reason,
                          "DateLastEdited": CandidateDatabase.timestamp()}
            self.table_update("Candidates", updateDict, "ID = " + str(ID))
            self.logger.info("Rejected candidate " + candidate.CandidateName + " for reason " + reason)
            print("Rejected candidate " + candidate.CandidateName + " for reason " + reason)
            self.db_connection.commit()
        else:
            self.logger.error("Couldn't find target with ID " + ID + ". Can't update.")
            return None
        return ID


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s', filename='libFiles/candidateDb.log',
                        encoding='utf-8', datefmt='%m/%d/%Y %H:%M:%S', level=logging.DEBUG)
    db = CandidateDatabase("../candidate database.db", "Sage")

    db.logger.addFilter(genUtils.filter)

    candidate = Candidate("Test", "Test", Notes="test")
    ID = db.insertCandidate(candidate)
    db.removeCandidateByID(ID, "Because I want to !")
