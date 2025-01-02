import sys, os
from os.path import abspath, join, dirname
import requests
import numpy as np
from astropy.io import fits
from astropy.coordinates import SkyCoord, Angle
from astropy.units import Quantity
import astropy.units as u
import socketio.exceptions
from alora.astroutils import calc_mean_fwhm, source_catalog
from alora.config import config
from alora.observatory.interfaces import PlateSolve
import socketio
import threading

acfg = config["ASTROMETRY"]

class Astrometry(PlateSolve):
    def __init__(self, write_out=print):
        super().__init__(write_out)
        self.sio = socketio.Client()
        self.current_job_id = None
        self.job_done_event = threading.Event()
        self.job_status = None
        try:
            self.connect()
        except socketio.exceptions.ConnectionError:
            self.write_out("Could not connect to astrometry server. Will try again when needed.")
        
    def connect(self):
        self.sio.connect(f"http://localhost:{acfg['PORT']}")

    def reset(self):
        self.job_done_event.clear()
        self.connect()


    def solve(self,impath, *args, synchronous=True, **kwargs):
        with fits.open(impath) as hdul:
            header = hdul[0].header
            try:
                guess_coords = SkyCoord(Angle(header["OBJCTRA"],unit="hourangle"), Angle(header["OBJCTDEC"],unit="deg"))
            except Exception as e:
                self.write_out(f"Exception when getting coords from header for '{impath}' {str(e)}")
                guess_coords = None
            scale = config["CAMERA"]["FIELD_WIDTH"] # arcmin

        resp = solve(impath, guess_coords=guess_coords, scale=scale, scale_units="arcminwidth", *args, write_out=self.write_out, **kwargs)
        resp = resp.json()
        if synchronous:
            self.current_job_id = resp["job_id"]
            self.job_status = None
            self.write_out(f"Waiting for job {self.current_job_id} to finish...")
            @self.sio.on("job_finished")
            def job_finished(data):
                self.write_out(f"Got job finished event: {data}")
                if data["job_id"] == self.current_job_id:
                    self.job_status = data["status"]
                    self.write_out(f"Job {self.current_job_id} done. Status: {data['status']}")
                    self.sio.disconnect()
                    self.job_done_event.set()
                else:
                    self.write_out(f"Got job-finished event for job {data['job_id']}, but current job is {self.current_job_id}")
    
            self.job_done_event.wait()
            self.write_out("Job done.")
            self.reset()
        return self.job_status == "solved", resp["job_id"]

def solve(path, guess_coords:SkyCoord=None, scale:float=config["CAMERA"]["PIX_SCALE"], scale_units="arcsecperpix", *args, **kwargs):
    if guess_coords is not None:
        kwargs["ra"] = guess_coords.ra.deg
        kwargs["dec"] = guess_coords.dec.deg
        kwargs["radius"] = config["ASTROMETRY"]["SEARCH_RADIUS"]
    if scale is not None:
        kwargs["scale-units"] = scale_units
        kwargs["scale-low"] = scale*0.95
        kwargs["scale-high"] = scale*1.05
    return _solve(path, *args, **kwargs)

def gensolve(path, guess_ra=None, guess_dec=None, scale_lower=None, scale_upper=None, *args, **kwargs):
    if guess_ra is not None:
        kwargs["ra"] = guess_ra
    if guess_dec is not None:
        kwargs["dec"] = guess_dec
    if scale_lower is not None:
        kwargs["scale_lower"] = scale_lower
    if scale_upper is not None:
        kwargs["scale_upper"] = scale_upper

    return _solve(path, *args, **kwargs)

def _solve(filepath,write_out=print,extract=True, *args, **kwargs):
    kwargs["filepath"] = abspath(filepath)
    write_out(f"Solving {filepath}...")


    kwargs["tweak-order"] = 2
    # kwargs["objs"] = 1000
    # kwargs["uniformize"] = 0
    # kwargs["nsigma"]=5
    kwargs["flags"] = list(args) + ["--no-plots", "--crpix-center", "--overwrite", "-v"]
    write_out("Sending solve request...")

    endpoint = "cat_and_solve" if extract else "solve"

    return requests.post(f"http://localhost:{acfg['PORT']}/{endpoint}", json=kwargs, headers={"Content-Type": "application/json"}, timeout=8)


def main():
    path = sys.argv[1]
    ast = Astrometry()
    if os.path.isdir(path):
        for f in [f for f in os.listdir(path) if f.endswith(config["IMAGE_EXTENSION"])]:
            ast.solve(join(path,f))
    else:
        print(ast.solve_sync(path))

if __name__ == "__main__":
    main()