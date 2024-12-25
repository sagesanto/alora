import sys, os
from os.path import abspath, join, dirname
import requests
import numpy as np
from astropy.io import fits
from astropy.coordinates import SkyCoord, Angle
from astropy.units import Quantity
import astropy.units as u
from alora.astroutils import calc_mean_fwhm, source_catalog
from alora.config import config
from alora.observatory.interfaces import PlateSolve


acfg = config["ASTROMETRY"]

class Astrometry(PlateSolve):
    def solve(self,impath, *args, **kwargs):
        with fits.open(impath) as hdul:
            header = hdul[0].header
            guess_coords = SkyCoord(Angle(header["OBJCTRA"],unit="hourangle"), Angle(header["OBJCTDEC"],unit="deg"))
            scale = config["CAMERA"]["FIELD_WIDTH"] # arcmin

        resp = solve(impath, guess_coords=guess_coords, scale=scale, scale_units="arcminwidth", *args, write_out=self.write_out, **kwargs)
        return resp.json()

def solve(path, guess_coords:SkyCoord=None, scale:float=config["CAMERA"]["PIX_SCALE"], scale_units="arcsecperpix", *args, **kwargs):
    if guess_coords is not None:
        pass
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
        for f in [f for f in os.listdir(path) if f.endswith("fit")]:
            ast.solve(join(path,f))
    else:
        print(ast.solve(path))

if __name__ == "__main__":
    main()