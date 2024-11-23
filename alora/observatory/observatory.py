import os
import dotenv
from . import Telescope, Dome, Camera

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
        self.dome = Dome(os.getenv("DOME_ADDR"),os.getenv("DOME_USERNAME"),os.getenv("DOME_PASSWORD"), write_out=self.write_out)
        self.camera = Camera(write_out=self.write_out)

    def open(self):
        self.write_out("Parking telescope...")
        park_succeeded, error_code = self.telescope.park()
        if not park_succeeded:
            raise ChildProcessError(f"Failed to park telescope. Error code: {error_code}")
        assert self.telescope.parked
        self.write_out("Telescope parked.")
        self.write_out("Opening dome...")
        self.dome._open()
        self.write_out("Open!")

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