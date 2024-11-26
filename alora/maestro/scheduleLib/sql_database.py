import os
import sqlite3
from collections.abc import Iterable

class SQLDatabase:
    def __init__(self):
        self.db_connection = None
        self.db_cursor = None
        self.connected = False

    def open(self, path, check_same_thread=True, **kwargs):
        print("hi")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Could not find file '{path}'")

        det_types = sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
        if "detect_types" in kwargs:
            det_types = kwargs["detect_types"] | sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
            del kwargs["detect_types"]
        # no try. we arent cowards
        self.db_connection = sqlite3.connect(path, check_same_thread=check_same_thread, detect_types=det_types, **kwargs)
        print(self.db_connection)
        self.db_connection.row_factory = sqlite3.Row
        self.db_cursor = self.db_connection.cursor()
        self.connected = True

    def close(self):
        try:
            self.db_connection.close()
        except AttributeError:
            raise sqlite3.DatabaseError("Tried to close database but it was None!")
        self.db_connection = None
        self.db_cursor = None
        self.connected = False

    @property
    def isConnected(self):
        return self.connected
    
    def commit(self):
        self.db_connection.commit()

    def create_db(self,path, check_same_thread=False, **kwargs):
        """Create sqlite3 db and connect to it

        :param path: path to db
        :type path: str
        :type check_same_thread: bool, optional
        :returns:
        :rtype: None
        """
        dud = sqlite3.connect(path)  # make the db
        dud.close() # close it
        self.open(path,check_same_thread,**kwargs)  # reopen according to self.open

    def table_query(self, table_name, colnames, condition=None, vals=None):
        if condition is not None:
            if not isinstance(vals, Iterable):
                raise ValueError(f"SQL query vals must be an iterable, not {vals} ({type(vals)})")
            if isinstance(colnames,str):
                colnames = [colnames]
            colnames = ','.join(colnames)
            self.db_cursor.execute(f"SELECT {colnames} FROM {table_name} WHERE {condition}", vals)
            return self.db_cursor.fetchall()
        if condition is None:
            self.db_cursor.execute(f"SELECT {colnames} FROM {table_name}")
            return self.db_cursor.fetchall()

        return None

    def insert_record(self,table_name,record):
        """Insert single record into table

        :type table_name: str
        :param records: colname, val pairs of record to insert
        :type records: dict
        """
        colnames = ", ".join(record.keys())
        vals = ", ".join(['?']*len(record))
        stmt = f"INSERT INTO {table_name} ({colnames}) {vals}"
        self.db_connection.execute(stmt,list(record.values()))
        self.commit()


    @staticmethod
    def query_to_dict(query_results):
        """!
        Convert SQLite query results to a list of dictionaries.
        @param queryResults: List of SQLite query row objects.
        @return: List of dictionaries representing query results.
        """
        d = [dict(row) for row in query_results if row]
        return [{k: v for k, v in a.items() if v is not None} for a in d if a]
    
    def create_table(self):
        pass
