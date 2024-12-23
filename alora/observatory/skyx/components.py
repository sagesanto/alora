import os
from os.path import join, abspath, exists
import socket
import tomlkit
import numpy as np
from abc import ABC, abstractmethod, abstractproperty
from typing import Union, Callable, Tuple
import astropy.units as u
from astropy.units import Quantity
from astropy.coordinates import SkyCoord, Angle
from astropy.io import fits

from alora.config import config
from alora.observatory.interfaces import Telescope, Camera, PlateSolve
from alora.observatory.skyx.config import js_script_path

FILTER_WHEEL = {
    # L, B, G, R, N1, N2, N3
    "L": 0,
    "B": 1,
    "G": 2,
    "R": 3,
    "N1": 4,
    "N2": 5,
    "N3": 6,
}

class SkyXException(Exception):
    pass

def load_script(script_name,**kwargs):
    with open(join(js_script_path,script_name),"r") as f:
        s = "\n".join(f.readlines())
    if kwargs:
        for k,v in kwargs.items():
            if isinstance(v,bool): v = int(v)
            if f"{{{k}}}" not in s:
                raise ValueError(f"Script {script_name} does not contain variable {k}")
            s = s.replace("{{"+k+"}}",str(v))
    return s

def shhh(*args,**kwargs):
    pass

# https://stackoverflow.com/a/62277798
def is_socket_closed(sock: socket.socket, write_out=print) -> bool:
    try:
        # this will try to read bytes without blocking and also without removing them from buffer (peek only)
        sock.setblocking(0) 
        data = sock.recv(16, socket.MSG_PEEK)
        sock.setblocking(1)
        if len(data) == 0:
            return True
    except BlockingIOError:
        sock.setblocking(1)
        return False  # socket is open and reading from it would block
    except ConnectionResetError:
        sock.setblocking(1)
        return True  # socket was closed for some other reason
    except Exception as e:
        sock.setblocking(1)
        if "WinError 10057" not in str(e):  # winerror 10057 is not an unexpected error if socket closed
            write_out(f"Unexpected exception when checking if socket is closed: {e}")
        return True
    return False


class SkyXClient:
    HEADER = "/* Java Script */\n"
    def __init__(self,port, write_out=print):
        self.port = port
        self.socket = socket.socket()
        self.write_out = write_out
    
    def set_write_out(self,write_out):
        self.write_out = write_out
    
    def send(self,content):
        self.socket.sendall(bytes(SkyXClient.HEADER+content,encoding="UTF-8"))

    def connect(self):
        # safe to call even if already connected
        if is_socket_closed(self.socket, write_out=self.write_out):
                self.socket.connect(("localhost", self.port))
                self.write_out(f"Connected to TheSkyX on port {self.port}.")

    @property
    def connected(self):
        r = not is_socket_closed(self.socket,write_out=self.write_out)
        if r:
            return True
        self.write_out(f"WARNING [ALORA]: SkyXClient connection failed. SkyX connection will be unavailable.")
        return False
    
    def disconnect(self):
        if not is_socket_closed(self.socket,write_out=shhh):
            self.socket.close()

    def parse_response(self,rlen=1024):
        response = self.socket.recv(rlen).decode('UTF-8')
        if response is None or not response:
            return None, 1
        content, error = response.split("|")
        if error == "No error. Error = 0.":
            error = 0
        if error:
            raise ChildProcessError(f"SkyX execution of script failed. Response was {content} | {error}")
        return content.strip()


conn = SkyXClient(config["SKYX_PORT"])


class SkyXTelescope(Telescope):
    def __init__(self, write_out=print):
        super().__init__(write_out)
        self.conn = conn
        conn.set_write_out(write_out)
        try:
            self.conn.connect()
        except Exception as e:
            self.write_out(f"WARNING [ALORA]: SkyXClient connection failed. SkyX connection will be unavailable. Error: {e}")        
        self.check_pos_script = load_script("get_telescope_pos.js")
        if self.conn.connected:
            self.test_mount_conn()
        else:
            self.write_out("WARNING [ALORA]: Telescope object initialized but no connection to SkyX could be made")
    
    @property
    def pos(self):
        if not self.conn.connected:
            raise ConnectionError("Cannot check telescope position: no connection to SkyX.")
        self.conn.send(self.check_pos_script)
        resp = self.conn.parse_response()
        if resp == "Not connected":
            raise ChildProcessError(f"Unable to get telescope position. Response was {resp}")
        ra, dec = resp.split(" ")
        ra = float(ra)   
        dec = float(dec)
        return SkyCoord(ra=15*ra*u.deg,dec=dec*u.deg)  # ra comes in in hours
    
    def pretty_pos(self, hms=False):
        if hms:
            return self.pos.to_string("hmsdms")
        return self.pos.to_string("decimal")
    
    def test_mount_conn(self):
        if not self.conn.connected:
            raise ConnectionError("Cannot check mount connectivity: no connection to SkyX.")
        script = load_script("check_tel_conn.js")
        self.conn.send(script)
        r = self.conn.parse_response()
        if r == "0":
            self.write_out("Connection to SkyX succeeded but SkyX reports that it cannot connect to the telescope")
            return False
        if r == "1":
            return True
        self.write_out(f"WARNING [ALORA]: Unexpected response from mount connection test: {r}")
        return False

    @property
    def connected(self):
        try:
            return self.conn.connected and self.test_mount_conn()
        except ConnectionResetError:
            return False
        
    def park(self):
        if not self.conn.connected:
            raise ConnectionError("Cannot park telescope: no connection to SkyX.")
        self.conn.send(load_script("park_sync.js"))
        resp = self.conn.parse_response()
        if resp == "Could not connect to telescope":
            raise ConnectionError(f"Unable to park telescope. Response was {resp}")
        if resp == "1":
            return True, 0
        else:
            self.write_out(resp)
            error = self.check_last_slew_error()
            self.write_out(f"SkyX reports that parking failed with error code {error}")
            return False, error

    @property
    def parked(self):
        if not self.conn.connected:
            raise ConnectionError("Cannot check telescope parked status: no connection to SkyX.")
        self.conn.send(load_script("check_parked_status.js"))
        resp = self.conn.parse_response()
        if resp == "Not connected":
            raise ConnectionError("Connection to SkyX succeeded but SkyX reports that it cannot connect to the telescope")
        return resp == "true"
    
    def check_last_slew_error(self):
        if not self.conn.connected:
            raise ConnectionError("Cannot check last slew error: no connection to SkyX.")
        self.conn.send(load_script("check_last_slew_error.js"))
        return self.conn.parse_response()

    def slew(self, coord:SkyCoord, closed_loop=True,closed_exptime=1):
        if not self.conn.connected:
            raise ConnectionError("Cannot slew telescope: no connection to SkyX.")
        ra = coord.ra.hour
        dec = coord.dec.deg
        if closed_loop:
            pix_scale = config["CAMERA"]["PIX_SCALE"] / 2  # will do 2x2 binning for slews
            script = load_script("slew_closed_loop.js",ra=ra,dec=dec,exptime=closed_exptime,image_scale=pix_scale)
        else:
            script = load_script("slew_open_loop.js",ra=ra,dec=dec)
        self.conn.send(script)
        resp = self.conn.parse_response()
        if resp != "0":
            raise SkyXException(f"SkyX reports that slew failed. Response was {resp}")
    
    def home(self):
        if not self.conn.connected:
            raise ConnectionError("Cannot home telescope: no connection to SkyX.")
        self.conn.send(load_script("find_home.js"))
        resp = self.conn.parse_response()
        if resp == "0":
            return
        else:
            raise SkyXException(f"SkyX reports that homing failed with error code {resp}")
    
    def track_at_custom_rates(self,dRA:Quantity,dDec:Quantity):
        if not self.conn.connected:
            raise ConnectionError("Cannot track telescope: no connection to SkyX.")
        try:
            _dRA = dRA.to_value("arcsec/second")
            _dDec = dDec.to_value("arcsec/second")
        except Exception as e:
            _dRA = dRA.to_value("arcsec")
            _dDec = dDec.to_value("arcsec")
        script = load_script("start_custom_tracking.js",dRA=_dRA,dDec=_dDec)
        self.conn.send(script)
        resp = self.conn.parse_response()
        if resp != "1":
            raise SkyXException(f"SkyX reports that setting track rates failed. Response was {resp}")
    
    def track_sidereal(self):
        if not self.conn.connected:
            raise ConnectionError("Cannot track telescope: no connection to SkyX.")
        self.conn.send(load_script("start_sidereal_tracking.js"))
        resp = self.conn.parse_response()
        if resp != "1":
            raise SkyXException(f"SkyX reports that starting sidereal tracking failed. Response was {resp}")
    
    def stop_tracking(self):
        if not self.conn.connected:
            raise ConnectionError("Cannot stop tracking: no connection to SkyX.")
        self.conn.send(load_script("stop_tracking.js"))
        resp = self.conn.parse_response()
        if resp != "0":
            raise SkyXException(f"SkyX reports that stopping tracking failed. Response was {resp}")


class SkyXCamera(Camera):
    def __init__(self, write_out=print) -> None:
        super().__init__(write_out)
        self.conn = conn
        current_filter = None
        conn.set_write_out(write_out)
        try:
            self.conn.connect()
        except Exception as e:
            self.write_out(f"WARNING [ALORA]: SkyXClient connection failed. SkyX connection will be unavailable. Error: {e}")  
        if self.conn.connected:
            self.test_camera_conn()
        else:
            self.write_out("WARNING [ALORA]: Telescope object initialized but no connection to SkyX could be made")
        self.cam_status_script = load_script("check_camera_status.js")

    def test_camera_conn(self):
        if not self.conn.connected:
            raise ConnectionError("Cannot check camera connection: no connection to SkyX.")
        script = load_script("check_camera_conn.js")
        self.conn.send(script)
        r = self.conn.parse_response()
        if r != "1":
            self.write_out("WARNING [ALORA]: Connection to SkyX succeeded but SkyX reports that it cannot connect to the camera")
            self.write_out(f"WARNING [ALORA]: SkyX response: {r}")
            return False
        return True
    
    @property
    def connected(self):
        return self.conn.connected and self.test_camera_conn()

    def start_dataset(self, nframes, exptime, filter:str, outdir, exp_delay=0, name_prefix='im', binning=config["DEFAULTS"]["BIN"], asynchronous=True):
        if filter not in FILTER_WHEEL:
            raise ValueError(f"Invalid filter '{filter}'. Must be one of {list(FILTER_WHEEL.keys())}")
        filter = FILTER_WHEEL[filter]
        outdir = abspath(outdir)
        outdir = outdir.replace("\\","/")
        script = load_script("take_data.js",exptime=exptime,nframes=nframes,filter=filter,outdir=outdir, exp_delay=exp_delay, prefix=name_prefix,asynchronous=asynchronous, binning=binning)

        if not self.conn.connected:
            raise ConnectionError("Cannot take exposure: no connection to SkyX.")
        self.conn.send(script)
        if not asynchronous:
            r = self.conn.parse_response()
            if not r.endswith("success"):
                raise SkyXException(f"SkyX reports that the dataset failed: {r}")
            r = r.replace(" success","")
            if r != "Ready":
                self.write_out("WARNING [ALORA]: Camera not idle after synchronous dataset!")
                return True, r
            return True, 0  # success
        return None, 0  # async in progress
    
    def take_dataset(self, nframes, exptime, filter:str, outdir, exp_delay=0, name_prefix='im', binning=config["DEFAULTS"]["BIN"]):
        # synchronous version of start_dataset. works the same but strictly synchronous
        return self.start_dataset(nframes, exptime, filter, outdir, exp_delay=exp_delay, name_prefix=name_prefix, binning=binning, asynchronous=False)

    def add_to_pointing_model(self,exptime):
        # use AutoMap to take img, solve field, and add to pointing model
        if not self.conn.connected:
            raise ConnectionError("Cannot add to pointing model: no connection to SkyX.")
        # will always do 2x2 binning
        self.conn.send(load_script("add_to_pointing_model.js",exptime=exptime,image_scale=config["CAMERA"]["PIX_SCALE"]*2))
        return self.conn.parse_response()


class SkyXImageLink(PlateSolve):
    def __init__(self, write_out=print):
        super().__init__(write_out)
        self.conn = conn
        conn.set_write_out(write_out)
        try:
            self.conn.connect()
        except Exception as e:
            self.write_out(f"WARNING [ALORA]: SkyXClient connection failed. SkyX connection will be unavailable. Error: {e}")        
        if not self.conn.connected:
            self.write_out("WARNING [ALORA]: ImageLink object initialized but no connection to SkyX could be made")

    def solve(self,impath,**kwargs):
        if not self.conn.connected:
            raise ConnectionError("Cannot solve image: no connection to SkyX.")
        impath = impath.replace("\\","/")
        if not exists(impath):
            raise FileNotFoundError(f"Image file {impath} does not exist.")
        binning = kwargs.get("binning",-1)
        if binning == -1:
            # need to determine the binning
            binning = self.determine_image_binning(impath)
            self.write_out(f"Found binning: {binning}x{binning}")

        imscale = config["CAMERA"]["PIX_SCALE"] * binning
        print(f"Predicted imscale: {imscale} arcsec/pix")

        script = load_script("solve_image.js",impath=impath, imscale=imscale)
        self.conn.send(script)
        return self.conn.parse_response()
    
    def batch_solve(self,impaths,**kwargs):
        # batch solve images. must all have the same px scale!
        if not self.conn.connected:
            raise ConnectionError("Cannot solve image: no connection to SkyX.")
        
        impaths = [abspath(p).replace("\\","/") for p in impaths]
        for impath in impaths:
            if not exists(impath):
                raise FileNotFoundError(f"Image file {impath} does not exist.")
        
        binning = kwargs.get("binning",-1)
        if binning == -1:
            # need to determine the binning
            impath = impaths[0]
            binning = self.determine_image_binning(impath)
            self.write_out(f"Found binning: {binning}x{binning}")

        imscale = config["CAMERA"]["PIX_SCALE"] * binning
        print(f"Predicted imscale: {imscale} arcsec/pix")

        impaths_str = "\""+"\", \"".join(impaths)+"\""
        script = load_script("solve_images.js",impaths=impaths_str, imscale=imscale)
        self.conn.send(script)
        r = self.conn.parse_response()
        if len(r.split(" ") != len(impaths)):
            raise SkyXException(f"SkyX reports that batch solving failed. Response was {r}")
        res = [s for s in r.split(" ") if s]
        print(res)

    def determine_image_binning(self,impath):
        hdul = fits.open(impath)
        data = hdul[0].data
        return int(np.round(config["CAMERA"]["CCD_WIDTH_PIX"]/data.shape[1]))