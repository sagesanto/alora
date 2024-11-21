import os
import dotenv
from . import Telescope, Dome

class Observatory:
    def __init__(self):
        self.telescope = None
        self.dome = None
        self.connect()
    
    def connect(self):
        self.telescope = Telescope()
        dotenv.load_dotenv()
        self.dome = Dome(os.getenv("DOME_ADDR"),os.getenv("DOME_USERNAME"),os.getenv("DOME_PASSWORD"))
    
    def open(self):
        print("Parking telescope...")
        park_succeeded, error_code = self.telescope.park()
        if not park_succeeded:
            raise ChildProcessError(f"Failed to park telescope. Error code: {error_code}")
        assert self.telescope.parked
        print("Telescope parked.")
        print("Opening dome...")
        self.dome._open()
        print("Open!")

    def close(self):
        print("Parking telescope...")
        park_succeeded, error_code = self.telescope.park()
        if not park_succeeded:
            raise ChildProcessError(f"Failed to park telescope. Error code: {error_code}")
        assert self.telescope.parked
        print("Telescope parked.")
        print("Closing dome...")
        self.dome._close()
        print("Closed!")

o = Observatory()
print(f"Telescope is at {o.telescope.pos}")
o.open()
# o.close()

print(f"Telescope is at {o.telescope.pos}")
# o.connect()
# print(o.telescope.pos)
# print(o.telescope.park())
