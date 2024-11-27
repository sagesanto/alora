import sqlite3, os, sys, json, logging
from .sensor import SensorService
from datetime import datetime
from .telemetry_db import TelemetryDB
import rpyc
from rpyc.utils.server import ThreadedServer
from .utils import init_logger, read_json, get_timestamp
import traceback
from threading import Timer, Lock
import logging.handlers

from alora.observatory.config import config as cfg
from .config import telem_log_dir


dbpath = cfg['TELEM_DBPATH']
telem_port = int(cfg['TELEMETRY_PORT'])

class SensorConnection:
    def __init__(self, sensor_name: str, table_name: str, blueprint: dict, port: int, outgoing_connection = None):
        self.sensor_name = sensor_name
        self.table_name = table_name
        self.blueprint = blueprint
        self.port = port
        self.outgoing_connection = outgoing_connection


class ConnectedSensors:
    def __init__(self):
        self.__lock = Lock()
        self.__connected_sensors = {}

    def __enter__(self):
        self.__lock.acquire()
        return self.__connected_sensors

    def __exit__(self, exc_type, exc_value, traceback):
        self.__lock.release()
        return


class TelemetryService(rpyc.Service):
    def __init__(self):
        self.logger, self.logger_listener = init_logger(os.path.join(telem_log_dir,"telemetry.log"))
        self.logger.info("")
        self.logger.info("Session Started")
        self.connected_sensors = ConnectedSensors()
        TelemetryDB(dbpath, self.logger).make_uptime_table()
        self.sensor_reading_count = {}
        self.logger.info("Telemetry Service initialized.")
        self.poll()
        self.logger.info(self.connections_status())
        self.do_log_measurements = False
        self.do_polling = True
        self.do_async_polling(5)
        self.report_recent_measurements(report_interval=60)

    # should be registered on first connection of each sensor SESSION 
    def exposed_register_sensor(self, blueprint_jstr,port,table_name,sensor_name):
        sensor_blueprint = json.loads(blueprint_jstr)

        self.logger.info(f"Registering sensor {sensor_name}")

        db = TelemetryDB(dbpath, self.logger)
        
        with self.connected_sensors as connected_sensors:
            if sensor_name in connected_sensors.keys():
                raise ValueError(f"Sensor {sensor_name} already registered!")
        
            # connect back to the sensor
            outgoing_conn = rpyc.connect('localhost', port)
            
            new_sensor = SensorConnection(sensor_name, table_name, sensor_blueprint, port, outgoing_conn)
            connected_sensors[sensor_name] = new_sensor
            db.make_sensor_table(sensor_name,table_name, sensor_blueprint)
            db.commit()
            self.logger.info(f"Registered sensor {sensor_name}")
            try: 
                db.execute(f"ALTER TABLE SensorUptime ADD COLUMN {sensor_name} INTEGER DEFAULT 0;")
                self.logger.info(f"Created new column in SensorUptime table for sensor {sensor_name}")
                db.commit()
            except sqlite3.OperationalError as e:
                self.logger.debug("Not creating new column in SensorUptime table, already exists.")
            db.close()
        
        self.poll()
        self.logger.info(self.connections_status())


    @property
    def blueprint(self):
        d = None
        with self.connected_sensors as connected_sensors:
            d = {sensor_name: sensor.blueprint for sensor_name, sensor in connected_sensors.items()}.copy()
        return d

    @property
    def exposed_blueprint(self):
        return self.blueprint

    def deregister_sensor(self, sensor:SensorConnection):
        try:
            with self.connected_sensors as connected_sensors:
                connected_sensors.pop(sensor.sensor_name)
            self.logger.info(f"Deregistered sensor {sensor.sensor_name}")
        except Exception as e:
            self.logger.debug(f"Unable to deregister sensor: {repr(e)}")

    
    def on_connect(self, conn):
        self.logger.info(f"Sensor connected.")
        return super().on_connect(conn)

    def on_disconnect(self, conn):
        lock = Lock()
        lock.acquire()
        self.logger.info(f"Detected sensor disconnect. Polling...")
        self.poll()
        self.logger.info(self.connections_status())
        lock.release()
        return super().on_disconnect(conn)

    def connections_status(self):
        with self.connected_sensors as connected_sensors:
            if len(connected_sensors) == 0:
                self.do_log_measurements = False
                return "STATUS: No sensors connected."
            self.do_log_measurements = True
            inven = "Connected Sensors:"
            for sensor_name, sensor in connected_sensors.items():
                inven += f" {sensor_name} ({sensor.table_name}) on port {sensor.port} |"
            return inven

    def poll(self):
        try:
            to_remove = []
            with self.connected_sensors as connected_sensors:
                for _, sensor in connected_sensors.items():
                    try:
                        sensor.outgoing_connection.root.ping()
                    except Exception as e:
                        if isinstance(e,(EOFError, ConnectionResetError)):
                            to_remove.append(sensor)
                            continue
                        self.logger.error(f"ERROR during poll: {repr(e)}")
                        # print whole traceback
                        print(traceback.format_exc())
        except Exception as e:
            self.logger.error(f"ERROR during poll iteration: {repr(e)}")
            return
        lock = Lock()
        if not lock.acquire(False):
            self.logger.info(f"Polling is happening in another thread, skipping poll.")
            return
        for sensor in to_remove:
            self.logger.info(f"Sensor {sensor.sensor_name} disconnected.")
            self.deregister_sensor(sensor)
            continue
        lock.release()
        self.log_currently_up()
    
    def log_currently_up(self):
        try:
            with self.connected_sensors as connected_sensors:
                connectedSensorNames = connected_sensors.keys()
                db = TelemetryDB(dbpath, self.logger)
                stmnt = 'INSERT INTO SensorUptime(Timestamp'
                for sensor_name in connectedSensorNames:
                    stmnt += f', {sensor_name}'
                stmnt += f")\nValues (?{', ?'*len(connectedSensorNames)})"
                vals = [1] * len(connectedSensorNames)
                vals.insert(0, get_timestamp())
                db.execute(stmnt,vals)
                db.commit()
                db.close()
        except sqlite3.DatabaseError as e:
            self.logger.error(f"Error logging sensor uptime: {repr(e)}")
            db.close()

    def report_recent_measurements(self,report_interval):
        msg = f"No measurements in the last {report_interval} seconds: No sensors connected."
        if self.do_log_measurements:
            with self.connected_sensors as connected_sensors:
                if len(connected_sensors) == 0:
                    msg = f"No measurements in the last {report_interval} seconds: No sensors connected."
                else:
                    msg = f"Measurements logged in the last {report_interval} seconds:"
                    for sensor_name, _ in connected_sensors.items():
                        if sensor_name not in self.sensor_reading_count.keys():
                            count = 0
                        else:
                            count = self.sensor_reading_count[sensor_name]
                        msg += f" {sensor_name}: {count} measurements |"
            self.logger.info(msg)
        self.sensor_reading_count = {}
        t = Timer(report_interval, self.report_recent_measurements,args=[report_interval])
        t.daemon = True
        t.start()
        return msg

    def do_async_polling(self,interval):
        if self.do_polling:
            self.poll()
        t = Timer(interval, self.do_async_polling,args=[interval])
        t.daemon = True
        t.start()


    @classmethod
    def validate_jdict(cls, d: dict, expected_keys: list):
        for key in expected_keys:
            if key not in d.keys():
                raise ValueError(f"ERROR: JSON did not include '{key}'")
    
    # use this in a try except clause, send exception back to client
    def exposed_write_measurement(self, measurement_jstring: str): 
        try:
            mdict = json.loads(measurement_jstring)
            db = TelemetryDB(dbpath, self.logger)
            assert('SensorName' in mdict.keys())
            sensor_name = mdict['SensorName']
            with self.connected_sensors as connected_sensors:
                if sensor_name not in connected_sensors.keys():
                    raise ValueError(f"no such sensor '{sensor_name}'")
                table_name = connected_sensors[sensor_name].table_name
            # self.logger.info(f"Writing measurement from {sensor_name} to table {table_name}")
        except Exception as e:
            if isinstance(e,(EOFError, ConnectionResetError)):
                self.logger.error(f"Measurement Error: Sensor {sensor_name} disconnected during measurement")
                return
            self.logger.critical(f"ERROR in measurement write: {repr(e)}")
            self.logger.error(traceback.format_exc())   
        try:
            # we pass the string, not the dict!
            db.write_measurement(measurement_jstring, table_name)
            # self.logger.info(f"Wrote measurement from sensor {sensor_name} to table {table_name}.")
        except Exception as e:
            if isinstance(e,(EOFError, ConnectionResetError)):
                self.logger.error(f"Measurement Error: Sensor {sensor_name} disconnected during measurement")
                return
            self.logger.critical(f"ERROR writing measurement info msg: {repr(e)}")
            db.close()
            raise e
        try:
            db.commit()
            db.close()
        except Exception as e:
            msg = f"Could not commit to database: {repr(e)}"
            self.logger.critical(msg)
            db.close()
            raise sqlite3.DatabaseError(msg)
        
        if sensor_name not in self.sensor_reading_count.keys():
            self.sensor_reading_count[sensor_name] = 0
        self.sensor_reading_count[sensor_name] += 1

    def exposed_register_api_frontend(self, port: int):
        self.logger.info(f"Registered API Frontend on port {port}")

    def exposed_merge_fallback_db(self, fallback_dbpath: str, tablename: str):
        self.logger.info(f"Attempting to attach fallback database '{fallback_dbpath}'")
        assert(os.path.exists(fallback_dbpath))
        db = TelemetryDB(dbpath, self.logger)
        db.execute(f"ATTACH DATABASE '{fallback_dbpath}' AS fallback")
        db.execute(f"""
            CREATE TABLE merged AS
            SELECT * FROM main.{tablename}
            UNION ALL
            SELECT * FROM fallback.{tablename}
        """)
        db.execute("DETACH DATABASE fallback")
        db.execute(f"DROP TABLE {tablename}")
        db.execute(f"ALTER TABLE merged RENAME TO {tablename}")
        db.commit()
        db.close()
        self.logger.info(f"Successfully merged fallback database '{fallback_dbpath}'")

        
    def exposed_sql_query(self, query_string: str):
        print("Recieved query:",query_string)
        result, error = "", ""
        try:
            db = TelemetryDB(dbpath, self.logger)
            result, error =  db.query(query_string)
        except Exception as e:
            # raise e
            error = repr(e)
        return result, error


    def exposed_ping(self):
        return True

if __name__ == '__main__':
    server = ThreadedServer(TelemetryService(), port = telem_port, protocol_config = {"allow_all_attrs" : True})
    server.start()