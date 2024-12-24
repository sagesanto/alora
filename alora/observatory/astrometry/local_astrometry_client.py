import sys, os
from os.path import abspath
import requests
import numpy as np
from astropy.io import fits
from astropy.coordinates import SkyCoord, Angle
from astropy.units import Quantity
import astropy.units as u
from alora.astroutils import calc_mean_fwhm, source_catalog
from alora.config import config
from alora.observatory.interfaces import PlateSolve

class Astrometry(PlateSolve):
    def solve(self,impath, *args, **kwargs):
        self.write_out(f"Solving {impath}...")
        with fits.open(impath) as hdul:
            header = hdul[0].header
            guess_coords = SkyCoord(Angle(header["OBJCTRA"],unit="hourangle"), Angle(header["OBJCTDEC"],unit="deg"))
            scale = config["CAMERA"]["FIELD_WIDTH"]  # arcmin

        return solve(impath, guess_coords=guess_coords, scale=scale, scale_units="arcminwidth", *args, write_out=self.write_out **kwargs)

def main():
    path = sys.argv[1]
    ast = Astrometry()
    print(ast.solve(path).content)

def make_source_cat(data:np.ndarray):
    mean_fwhm = calc_mean_fwhm(data)
    cat = source_catalog(data,source_sigma=3,ncont=5,fwhm_pix=mean_fwhm)
    return cat["xcentroid","ycentroid"]

def solve(path, guess_coords:SkyCoord=None, scale:Quantity=config["CAMERA"]["PIX_SCALE"]*u.arcsec, *args, **kwargs,scale_units="arcsecperpix"):
    if guess_coords is not None:
        pass
        kwargs["ra"] = guess_coords.ra.deg
        kwargs["dec"] = guess_coords.dec.deg
        kwargs["radius"] = config["ASTROMETRY"]["SEARCH_RADIUS"]
    if scale is not None:
        kwargs["scale-low"] = scale.to_value("arcsec")*0.95
        kwargs["scale-high"] = scale.to_value("arcsec")*1.05
        kwargs["scale-units"] = scale_units

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

def _solve(filepath, *args, **kwargs,write_out=print):
    # kwargs["filepath"] = abspath(path)
    write_out(f"Solving {filepath}...")
    with fits.open(filepath) as hdul:
        data = hdul[0].data

    write_out("Making source catalog...")
    cat = make_source_cat(data)
    if ".fits" in filepath:
        newpath = filepath.replace(".fits", "_cat.fits")
    else:
        newpath = filepath.replace(".fit", "_cat.fits")

    cat.write(newpath, format='fits', overwrite=True)
    # print("cat path:",newpath)

    kwargs["width"] = data.shape[1]
    kwargs["height"] = data.shape[0]
    kwargs["x-column"] = "xcentroid"
    kwargs["y-column"] = "ycentroid"
    kwargs["fitspath"] = filepath  # specify the fits path that the sol will be written into, even tho the actual file the solution is derived from is a catalog
    kwargs["filepath"] = newpath

    kwargs["tweak-order"] = 2
    # kwargs["objs"] = 1000
    # kwargs["uniformize"] = 0
    # kwargs["nsigma"]=5
    kwargs["flags"] = list(args) + ["--no-plots", "--crpix-center", "--overwrite", "-v"]
    write_out("Sending solve request...")
    return requests.post("http://localhost:5555/solve", json=kwargs, headers={"Content-Type": "application/json"})

if __name__ == "__main__":
    main()