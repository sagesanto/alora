import json
import sqlite3
from .utils import get_timestamp


class TelemetryDB:
    def __init__(self, dbpath, logger):
        self.logger = logger
        self.dbpath = dbpath
        self.connect()

    def connect(self):
        self.conn = sqlite3.connect(database=self.dbpath, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()
    
    def make_uptime_table(self):
        create_statement = """CREATE TABLE IF NOT EXISTS "SensorUptime" ("Timestamp"	FLOAT NOT NULL)"""
        self.execute(create_statement)
    
    def make_blueprint_table(self):
        create_statement = """CREATE TABLE IF NOT EXISTS "Blueprints" ("SensorName"\tTEXT NOT NULL,\n"Blueprint"\tTEXT NOT NULL,\n"TableName"\tTEXT NOT NULL,\nPRIMARY KEY (SensorName,Blueprint,TableName))"""
        print(create_statement)
        self.execute(create_statement)        

    def close(self):
        self.conn.close()
    
    def refresh(self):
        self.close()
        self.connect()

    def execute(self, sql_statement, vals=None):
        if vals:
            self.cur.execute(sql_statement, vals)
        else:
            self.cur.execute(sql_statement)

    def commit(self):
        self.conn.commit()

    def log_blueprint(self,sensor_name,table_name, sensor_blueprint):
        try:
            self.execute("INSERT INTO Blueprints (SensorName,Blueprint,TableName) VALUES (?,?,?)",[sensor_name,str(sensor_blueprint),table_name])
        except sqlite3.IntegrityError:  # unique constraint violated
            self.execute("UPDATE Blueprints SET Blueprint = ?, TableName = ? WHERE SensorName=?",[str(sensor_blueprint),table_name,sensor_name])
        
    # if not exists, create table for sensor
    def make_sensor_table(self, sensor_name, table_name, sensor_blueprint: dict):
        self.log_blueprint(sensor_name,table_name,sensor_blueprint)
        create_statement = f'''CREATE TABLE "{table_name}" (\n"Timestamp"\tFLOAT NOT NULL,\n"SensorName"\tSTRING NOT NULL,\n"ID"\tINTEGER,'''

        for col, val in sensor_blueprint.items():
            dtype = val[0]
            create_statement += f'\n"{col}"\t{dtype},'

        create_statement += f'\nPRIMARY KEY("ID" AUTOINCREMENT)\n)'
        try:
            self.execute(create_statement)
            self.logger.info(f"Creating table '{table_name}' for sensor {sensor_name} with blueprint {sensor_blueprint}")
        except sqlite3.OperationalError as e:
            if (f"table \"{table_name}\" already exists") in str(e):
                self.logger.info(f"Did not need to create table for sensor {sensor_name} (already exists).")
            else:
                raise e
            
    @classmethod
    def create_sql_statement(cls, measurement_dict, table_name):
        if "Timestamp" not in measurement_dict.keys():
            measurement_dict["Timestamp"] = get_timestamp()
        stmnt = f'INSERT INTO {table_name}('
        for col, _ in measurement_dict.items():
            stmnt += f'{col}, '
        stmnt = stmnt[:-2] # fucking ugly
        stmnt += f")\nValues (?{', ?'*(len(measurement_dict)-1)})"
        vals = list(measurement_dict.values())
        return stmnt, vals
    
    def write_measurement(self, measurement_jstring, table_name: str):
        mdict = json.loads(measurement_jstring)
        sensor_name = mdict['SensorName']
        
        stmnt, vals = self.create_sql_statement(mdict, table_name)

        try:
            self.execute(stmnt, vals)
            # self.logger.info(f"Wrote measurement from sensor {sensor_name} to table {table_name}.")
        except Exception as e:
            raise sqlite3.DatabaseError(f"could not insert measurement into table '{table_name}': {repr(e)}")
        try:
            self.commit()
        except Exception as e:
            raise sqlite3.DatabaseError(f"could not commit to database: {repr(e)}")

    @staticmethod
    def query_to_dict(queryResults):
        """!
        Convert SQLite query results to a list of dictionaries.
        @param queryResults: List of SQLite query row objects.
        @return: List of dictionaries representing query results.
        """
        dictionary = [dict(row) for row in queryResults if row]
        return [{k: v for k, v in a.items() if v is not None} for a in dictionary if a]

    def query(self, sql_statement):
        """!Query table based on condition. If no condition given, will return the whole table - if this isn't what you want, be careful!
        Return
        ------
        rows : dict or list
            Python list of dicts, indexed by column name
        """
        if "INSERT INTO" in sql_statement or "UPDATE" in sql_statement or "DELETE" in sql_statement:
            raise ValueError("Query is read-only. Do not attempt to insert records this way; use the sensor API instead.")
        try:
            self.execute(sql_statement)
        except sqlite3.OperationalError as err:
            self.logger.error(f"Failed to query tables with statement '{sql_statement}'")
            self.logger.error('sqlite error : %s' % err)
            return {}, repr(err)
        
        res = self.cur.fetchall()
        result = self.query_to_dict(res)
        if result:
            self.logger.info("Query: Retrieved " + str(len(result)) + " record(s) in response to query")
            return result, ""
        self.logger.warning(f"Got no rows in response to query '{sql_statement}'")
        return {}, ""
    

