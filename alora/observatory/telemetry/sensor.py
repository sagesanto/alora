from abc import ABCMeta, abstractmethod
import rpyc, logging, os, json, sys
from rpyc.utils.server import ThreadedServer
import socket
import time
from os.path import join, exists, dirname, splitext, basename
from threading import Timer, Lock
from .utils import init_logger
from .telemetry_db import TelemetryDB
import logging.handlers
import queue, threading
import atexit
import inspect

from alora.config import config as cfg
from alora.observatory.telemetry.config import telem_log_dir, service_dir, fallback_dir

telem_port = int(cfg['TELEMETRY_PORT'])
valid_sqlite_datatypes = ['INT', 'INTEGER', 'TINYINT', 'SMALLINT', 'MEDIUMINT', 'BIGINT', 'UNSIGNED BIG INT', 'INT2', 'INT8', 'CHARACTER', 'VARCHAR', 'VARYING CHARACTER', 'NCHAR', 'NATIVE CHARACTER', 'NVARCHAR', 'TEXT', 'CLOB', 'BLOB', 'REAL', 'DOUBLE', 'DOUBLE PRECISION', 'FLOAT', 'NUMERIC', 'DECIMAL', 'BOOLEAN', 'DATE', 'DATETIME']


def is_port_available(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) != 0

def find_available_port(start_port, end_port):
    for port in range(start_port, end_port):
        if is_port_available(port):
            return port
    return None

BANNED_BLUEPRINT_CHARS = ["%", "\\"]

class SensorService(rpyc.Service, metaclass=ABCMeta):
    @abstractmethod
    def __init__(self, sensor_name: str, table_name: str, blueprint: dict, polling_interval,local_db_name="default"):
        self.sensor_name = sensor_name
        self.table_name = table_name
        self.blueprint = blueprint
        for k,v in self.blueprint.items():
            for c in BANNED_BLUEPRINT_CHARS:
                if c in k or c in v[0] or c in v[1]:
                    raise ValueError(f"Character '{c}' is not allowed in blueprint!")
        self.interval = polling_interval
        self.logger, self.logger_listener = self.init_sensor_logger(os.path.join(telem_log_dir,f"{self.sensor_name}.log"))
        if local_db_name == "default":
            local_db_name = join(fallback_dir,f"local_{self.sensor_name}_fallback.db")
        self.local_db_name = local_db_name
        self.logger.info(f"Initializing sensor {self.sensor_name}")
        for _, value in blueprint.items():
            if value[0].upper() not in valid_sqlite_datatypes:
                raise AttributeError(f'{value[0]} is not a valid sqlite datatype. Valid types are: {valid_sqlite_datatypes}')

    def start(self):
        self.logger.info("Searching for available port")
        self.port = find_available_port(18000, 65535)
        if self.port is None:
            raise ValueError("No available ports found")
        self.logger.info(f"Found available port {self.port}")

        self.server_thread = threading.Thread(target=self._start, daemon=True, name=f"{self.sensor_name}_server_thread")
        self.server = None
        self.logger.info("Starting sensor server.")
        self.server_thread.start()

        self.logger.info(f"Sensor {self.sensor_name} started on port {self.port}")
        self.logger.info(f"Sensor {self.sensor_name} blueprint: {self.blueprint}")

        self.num_measurements = 0

        self.local = False  # will set to true if we can't connect and fallback to writing locally
        self.telemetry_conn = None
        self.blueprint_jstr = json.dumps(self.blueprint) 
        self.logger.info("Connecting to telemetry server")
        try:
            self.connect_to_telemetry()
            self.merge_fallback_db()
        except ConnectionError as e:
            self.logger.error(f"Could not connect to telemetry server after 3 attempts.")
            self.use_local_db()
        self.stop_measuring = False
        atexit.register(self.stop_taking_measurements)
        self.start_taking_measurements()
        self.log_measurement_count(60)

    def init_sensor_logger(self,filepath):
        # dateFormat = '%m/%d/%Y %H:%M:%S'
        # LOGFORMAT = f" %(asctime)s %(log_color)s%(levelname)-5s%(reset)s {self.sensor_name.center(8)} | %(log_color)s%(message)s%(reset)s"
        # formatter = ColoredFormatter(LOGFORMAT, datefmt=dateFormat)
        # return init_logger(filepath,formatter)
        return init_logger(filepath)


    def write_local(self, measurement):
        db = TelemetryDB(self.local_db_name, self.logger)
        db.write_measurement(measurement,table_name=self.table_name)
        
    def use_local_db(self):
        self.logger.error("Falling back to local writing")
        # we'll use a local identical db (but with only our table) to write to
        db = TelemetryDB(self.local_db_name, self.logger)
        db.make_sensor_table(self.sensor_name, self.table_name, self.blueprint)
        self.local = True
        self.write = self.write_local

    def _start(self):
        self.server = ThreadedServer(self, port = self.port, protocol_config = {"allow_all_attrs" : True})
        self.server.start()
    
    @property
    def exposed_remote_sensor_name(self):
        return self.sensor_name
    
    @property
    def exposed_table_name(self):
        return self.table_name
    
    @property
    def exposed_blueprint(self):
        return self.blueprint_jstr
    
    @property
    def exposed_port(self):
        return self.port

    def connect_to_telemetry(self, attempts = 3):
        for a in range(attempts):
            try:
                self.telemetry_conn = rpyc.connect('localhost', telem_port, service=self, config={"allow_all_attrs" : True, "connid" : self.sensor_name})
                if self.telemetry_conn is not None:
                    self.telemetry_conn.root.register_sensor(self.blueprint_jstr, self.port,self.table_name,self.sensor_name)
                    self.local = False
                    self.write = rpyc.async_(self.telemetry_conn.root.write_measurement)        
                    # self.telemetry_conn.root.register_sensor(self, self.blueprint_items)
                    self.logger.info("Connected to telemetry server")
                    return
            except ConnectionRefusedError as e:
                # print(e)
                if a < attempts - 1:
                    self.logger.error("Could not connect to telemetry server, retrying...")
                    time.sleep(0.1)
        raise ConnectionError(f"Could not connect to telemetry server after {attempts} attempts")

    def stop_taking_measurements(self):
        self.stop_measuring = True

    # use async rpyc callbacks to send measurements to telemetry server every interval seconds
    
    def merge_fallback_db(self):
        if os.path.exists(self.local_db_name):
            self.logger.info("Merging local db with telemetry db")
            self.telemetry_conn.root.merge_fallback_db(self.local_db_name, self.table_name)
            self.logger.info("Merged local db with telemetry db")
            # we need to be able to remove the db!!!
            threading.Thread(target=self.delete_fallback_db, daemon=True, name="fallback_deletion_server_thread").start()
        else:
            self.logger.info("All caught up: no local db to merge")

    def delete_fallback_db(self):
        while True:
            if os.path.exists(self.local_db_name):
                try:
                    os.remove(self.local_db_name)
                    self.logger.info("Deleted local db")
                    return
                except OSError as e:
                    self.logger.info(f"ERROR: Could not delete local db ({repr(e)}) , trying again...")
                    time.sleep(5)

    def check_telem_connection(self):
        try:
            return self.telemetry_conn.root.ping()
        except:
            return False

    def send_measurement(self,measurement):
        if self.stop_measuring:
            self.logger.info("Can't take measurement: stopped!")
            return
        measurement['SensorName'] = self.sensor_name
        i = json.dumps(measurement)
        if self.local:
            try:
                self.connect_to_telemetry(attempts=1)
                self.merge_fallback_db()
            except ConnectionError:
                pass
        elif not self.check_telem_connection():
            self.use_local_db()

        self.logger.debug(f"Writing measurement {measurement}")
        self.write(i)
        self.logger.debug(f"Wrote measurement.")
        self.num_measurements += 1

    def ping(self):
        return True

    def __repr__(self):
        return f"SensorService(sensor_name={self.sensor_name}, table_name={self.table_name}, blueprint={self.blueprint}, port={self.port})"

    def log_measurement_count(self,log_interval_seconds):
        msg = f"Logged {self.num_measurements} measurements in the last {log_interval_seconds} seconds."
        if not self.stop_measuring:
            self.logger.info(msg)
        self.num_measurements = 0
        t = Timer(log_interval_seconds, self.log_measurement_count, args=[log_interval_seconds])
        t.daemon = True
        t.start()
        return msg

    @abstractmethod
    def start_taking_measurements(self):
        # should begin the process of taking measurements
        pass

    @abstractmethod
    def take_measurement(self):
        # should take a measurement, then send it using send_measurement()
        pass

    def write_service(self):
        if sys.platform == "darwin":
            raise NotImplementedError("Service writing not implemented for MacOS")
        if "linux" in sys.platform:
            raise NotImplementedError("Service writing not implemented on Linux")
        if sys.platform == "win32" or sys.platform == "cygwin" or sys.platform == "msys":
            service_path = join(service_dir,f"{self.sensor_name}_serv.bat")   
            classname = type(self).__name__
            class_modfile = inspect.getmodule(type(self)).__file__
            py_path = join(service_dir,f"{self.sensor_name}_serv.py")   
            with open(py_path,"w+") as f:
                f.write("import sys,time\n")
                f.write(f"sys.path.append(r'{dirname(class_modfile)}')\n")
                f.write(f"from {splitext(basename(class_modfile))[0]} import {classname}\n")
                f.write(f"s = {classname}('{self.sensor_name}', '{self.table_name}', {self.blueprint}, {self.interval}, r'{self.local_db_name}')\n")
                f.write(f"s.start()\n")
                f.write("while True:\n")
                f.write("\ttime.sleep(0.5)")
            with open(service_path,"w+") as f:
                f.write("@echo off\n")
                f.write(f"call {join(dirname(sys.executable),'activate.bat')}\n")
                f.write(f"python {py_path}")
            return service_path

    def start_service(self):
        if sys.platform == "darwin":
            raise NotImplementedError("Service running not implemented for MacOS")
        if "linux" in sys.platform:
            raise NotImplementedError("Service running not implemented on Linux")
        if sys.platform == "win32" or sys.platform == "cygwin" or sys.platform == "msys":
            spath = self.write_service()
            # sussss
            os.system(f"nssm install Alora{self.sensor_name.replace(' ','')} {spath} DisplayName \"Alora {self.sensor_name}\" ")


if __name__ == "__main__":
    pass