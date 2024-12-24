import sys, os
import requests

from astropy.io import fits
from astropy.coordinates import SkyCoord, Angle
from astropy.units import Quantity
import astropy.units as u

from alora.observatory.config import config

path = sys.argv[1]

def fancy_solve(path, *args, **kwargs):
    with fits.open(path) as hdul:
        header = hdul[0].header
        guess_coords = SkyCoord(Angle(header["OBJCTRA"],unit="hourangle"), Angle(header["OBJCTDEC"],unit="deg"))
        scale = config["CAMERA"]["PIX_SCALE"]*u.arcsec*header["XBINNING"]

    return solve(path, guess_coords=guess_coords, scale=scale, *args, **kwargs)

def solve(path, guess_coords:SkyCoord=None, scale:Quantity=config["CAMERA"]["PIX_SCALE"]*u.arcsec, *args, **kwargs):
    if guess_coords is not None:
        pass
        kwargs["ra"] = guess_coords.ra.deg
        kwargs["dec"] = guess_coords.dec.deg
        kwargs["radius"] = config["ASTROMETRY"]["SEARCH_RADIUS"]
    if scale is not None:
        kwargs["scale-low"] = scale.to_value("arcsec")*0.95
        kwargs["scale-high"] = scale.to_value("arcsec")*1.05
        kwargs["scale-units"] = "arcsecperpix"

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

def _solve(path, *args, **kwargs):
    kwargs["filepath"] = path
    kwargs["tweak-order"] = 2
    # kwargs["objs"] = 1000
    # kwargs["uniformize"] = 0
    # kwargs["nsigma"]=5
    kwargs["flags"] = list(args) + ["--no-plots", "--crpix-center", "--overwrite", "-v"]
    return requests.post("http://localhost:5555/solve", json=kwargs, headers={"Content-Type": "application/json"})\

if __name__ == "__main__":
    print(fancy_solve(path).content)