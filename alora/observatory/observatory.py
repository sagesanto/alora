import os
import dotenv
from .skyx import SkyXTelescope, SkyXCamera
from .relay_dome import RelayDome
from .data_archive import Observation
from alora.config import config
import requests

class AloraError(Exception):
    pass

class Observatory:
    def __init__(self, write_out=print):
        self.write_out = write_out
        self.telescope = None
        self.dome = None
        self.camera = None
        self.connect()
    
    def connect(self, telescope=SkyXTelescope, dome=RelayDome, camera=SkyXCamera):
        self.telescope = telescope(write_out=self.write_out)
        dotenv.load_dotenv()
        self.dome = dome(write_out=self.write_out)
        self.camera = camera(write_out=self.write_out)

    def open(self,do_home=True):
        self.write_out("Checking whether it is safe to open the dome...")
        if not self.safe_to_open:
            raise AloraError("Watchdog reports that it is not safe to open the dome.")
        self.write_out("Parking telescope...")
        park_succeeded, error_code = self.telescope.park()
        if not park_succeeded:
            raise AloraError(f"Failed to park telescope. Error code: {error_code}")
        assert self.telescope.parked
        self.write_out("Telescope parked.")
        self.write_out("Opening dome...")
        self.dome._open()
        self.write_out("Opened dome.")
        if do_home:
            self.write_out("Homing telescope...")
            self.telescope.home()
            self.write_out("Homed telescope.")

    def close(self):
        self.write_out("Parking telescope...")
        park_succeeded, error_code = self.telescope.park()
        if not park_succeeded:
            raise AloraError(f"Failed to park telescope. Error code: {error_code}")
        assert self.telescope.parked
        self.write_out("Telescope parked.")
        self.write_out("Closing dome...")
        self.dome._close()
        self.write_out("Closed!")

    @property
    def safe_to_open(self):
        try:
            watchdog_status = requests.get(f"http://localhost:{config['WATCHDOG_PORT']}/status").json()['safe_to_open']
            return watchdog_status
        except Exception as e:
            raise AloraError(f"Couldn't get watchdog status when checking whether it was safe to open the dome: {e}") from e

    # def queue_observation():