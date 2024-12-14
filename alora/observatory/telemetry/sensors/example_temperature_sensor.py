# Sage and Pei 2023
# example temperature sensor class, currently returns only random values unless subclassed
# mostly for testing

import rpyc
import random
from rpyc.utils.server import ThreadedServer
import time
from threading import Timer
from alora.observatory.telemetry.sensor import SensorService

class TemperatureSensorService(SensorService):
    def __init__(self, sensor_name: str, table_name: str, blueprint: dict, polling_interval=1, local_db_name="default"):
        super().__init__(sensor_name, table_name, blueprint, polling_interval, local_db_name)
        self.logger.info(f"Initialized Temperature Sensor {self.sensor_name}")

    def start_taking_measurements(self):
        self.stop = False
        self.logger.info(f"Starting to take measurements with interval {self.interval}")
        self.take_measurement()

    def take_measurement(self):
        if self.stop:
            self.logger.info("Can't take measurement: stopped!")
            return
        temp = random.randint(0, 100)
        measurement = {"temperature": temp, "SensorName": self.sensor_name}

        self.send_measurement(measurement)
        t = Timer(self.interval, self.take_measurement)
        t.daemon = True
        t.start()
        
    

if __name__ == "__main__":
    s1 = TemperatureSensorService("PT100", "Temperature", {"temperature": ["INTEGER", "degrees C"]})
    s1.start()
    # s2 = TemperatureSensorService("PT101", "Temperature", {"temperature": ["INTEGER", "degrees C"]})
    # s3 = TemperatureSensorService("PT102", "Temperature", {"temperature": ["INTEGER", "degrees C"]})
    
    # sensor.start_sending_measurements()
    time.sleep(1000)
    # sensor.stop_sending_measurements()
    # time.sleep(3)
