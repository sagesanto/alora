import os
import requests
import dotenv
import numpy as np
import time

from astropy.coordinates import SkyCoord, Angle
from astropy.io import fits
import astropy.units as u

from alora.astroutils.observing_utils import J2000_to_apparent
from .skyx import SkyXTelescope, SkyXCamera
from .relay_dome import RelayDome
from .astrometry import Astrometry
from .data_archive import Observation
from alora.config import config


class AloraError(Exception):
    pass

class Observatory:
    def __init__(self, write_out=print):
        self.write_out = write_out
        self.telescope = None
        self.dome = None
        self.camera = None
        self.plate_solver=None
        self.job_state = "free"
        self.dome_state = "open"  # we assume the dome is open when we start, but we don't actually know for now
        self.connect()
    
    def connect(self, telescope=SkyXTelescope, dome=RelayDome, camera=SkyXCamera, plate_solver=Astrometry):
        self.telescope = telescope(write_out=self.write_out)
        dotenv.load_dotenv()
        self.dome = dome(write_out=self.write_out)
        self.camera = camera(write_out=self.write_out)
        self.plate_solver = plate_solver(write_out=self.write_out)

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
        self.dome_state = "open"

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
        self.dome_state = "closed"

    @property
    def safe_to_open(self):
        try:
            watchdog_status = requests.get(f"http://localhost:{config['WATCHDOG_PORT']}/status").json()['safe_to_open']
            return watchdog_status
        except Exception as e:
            raise AloraError(f"Couldn't get watchdog status when checking whether it was safe to open the dome: {e}") from e

    def slew(self, coord:SkyCoord, closed_loop=True,closed_exptime=2, epoch="J2000"):
        if epoch not in ["J2000","apparent"]:
            raise ValueError(f"Invalid epoch: {epoch}. Valid values are 'J2000' and 'apparent'.")
        if epoch == "J2000":
            # need to convert to apparent for skyx
            coord = J2000_to_apparent(coord)
        self.write_out(f"Slewing to {coord}")
        self.telescope.slew(coord,closed_loop=closed_loop,closed_exptime=closed_exptime)
        if closed_loop:
            closed_path = config["CLOSED_LOOP_OUTDIR"]
            offset = None
            while offset is None or offset > config["CLOSED_LOOP_TOLERANCE"]*u.arcmin:
                self.telescope.track_sidereal()
                self.write_out("Giving telescope two seconds to start tracking...")
                time.sleep(2) # give it some time to start tracking
                success, fnames, status = self.camera.take_dataset(1,closed_exptime,"CLEAR",closed_path)
                im = fnames[0]
                status, job_id = self.plate_solver.solve(im,synchronous=True)
                if not status:
                    self.write_out(f"Failed to solve image {im}. Slewing by a field and looping again")
                    # slew by a field width and height, then check offset
                    self.telescope.jog(config["CAMERA"]["FIELD_WIDTH"]*u.arcmin,config["CAMERA"]["FIELD_HEIGHT"]*u.arcmin)
                    continue
                with fits.open(im) as hdul:
                    ra = hdul[0].header["CRVAL1"]*u.deg
                    dec = hdul[0].header["CRVAL2"]*u.deg
                actual_pos = SkyCoord(ra,dec)
                actual_pos = J2000_to_apparent(actual_pos)
                offset = actual_pos.separation(coord)
                self.write_out(f"Tried to slew to {coord}. Actual position is {actual_pos}. Offset is {offset}.")
                if offset > config["CLOSED_LOOP_TOLERANCE"]*u.arcmin:
                    self.write_out(f"Offset is {offset}. Doing another slew loop.")
                    self.telescope.jog((coord.ra-actual_pos.ra)*np.cos(coord.dec.rad),coord.dec-actual_pos.dec)

    # def queue_observation():