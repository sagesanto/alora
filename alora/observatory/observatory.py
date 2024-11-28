import os
import dotenv
from . import Telescope, Dome, Camera
from .data_archive import Observation
from .config import get_credential  

class Observatory:
    def __init__(self, write_out=print):
        self.write_out = write_out
        self.telescope = None
        self.dome = None
        self.camera = None
        self.connect()
    
    def connect(self):
        self.telescope = Telescope(write_out=self.write_out)
        dotenv.load_dotenv()
        self.dome = Dome(get_credential("dome",'addr'), get_credential("dome",'user'),get_credential("dome",'password'), write_out=self.write_out)
        self.camera = Camera(write_out=self.write_out)

    def open(self,do_home=True):
        self.write_out("Parking telescope...")
        park_succeeded, error_code = self.telescope.park()
        if not park_succeeded:
            raise ChildProcessError(f"Failed to park telescope. Error code: {error_code}")
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
            raise ChildProcessError(f"Failed to park telescope. Error code: {error_code}")
        assert self.telescope.parked
        self.write_out("Telescope parked.")
        self.write_out("Closing dome...")
        self.dome._close()
        self.write_out("Closed!")

    # def queue_observation():