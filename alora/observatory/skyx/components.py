from os.path import join
import socket
import tomlkit
import astropy.units as u
from astropy.coordinates import SkyCoord

from alora.observatory.config import config_path
from .config import js_script_path

def load_script(script_name):
    with open(join(js_script_path,script_name),"r") as f:
        return "\n".join(f.readlines())

with open(config_path,"rb") as f:
    config = tomlkit.load(f)

class SkyXClient:
    HEADER = "/* Java Script */\n"
    def __init__(self,port):
        self.port = port
        self.socket = socket.socket()
        self.socket.connect(("localhost", port))
        self.test_conn()
    
    def send(self,content):
        self.socket.send(bytes(SkyXClient.HEADER+content,encoding="UTF-8"))

    def test_conn(self):
        script = load_script("check_tel_conn.js")
        self.send(script)
        r = self.parse_response()
        if r == "0":
            raise ConnectionError(f"Connection to SkyX succeeded but SkyX reports that it cannot connect to the telescope")
        print(f"Connected to TheSkyX on port {self.port}.")

    def parse_response(self,rlen=1024):
        response = self.socket.recv(rlen).decode('UTF-8')
        if response is None:
            return None, 1
        content, error = response.split("|")
        if error == "No error. Error = 0.":
            error = 0
        if error:
            raise ChildProcessError(f"SkyX execution of script failed. Response was {content} | {error}")
        return content.strip()

conn = SkyXClient(config["SKYX_PORT"])

class Telescope:
    def __init__(self):
        self.conn = conn
        self.check_pos_script = load_script("get_telescope_pos.js")
    
    @property
    def pos(self):
        self.conn.send(self.check_pos_script)
        resp = self.conn.parse_response()
        if resp == "Not connected":
            raise ChildProcessError(f"Unable to get telescope position. Response was {resp}")
        ra, dec = resp.split(" ")
        ra = float(ra)
        dec = float(dec)
        return SkyCoord(ra=ra*u.deg,dec=dec*u.deg)
    
    def park(self):
        self.conn.send(load_script("park_sync.js"))
        resp = self.conn.parse_response()
        if resp == "Could not connect to telescope":
            raise ConnectionError(f"Unable to park telescope. Response was {resp}")
        if resp == "1":
            return True, 0
        else:
            print(resp)
            error = self.check_last_slew_error()
            print(f"SkyX reports that parking failed with error code {error}")
            return False, error

    @property
    def parked(self):
        self.conn.send(load_script("check_parked_status.js"))
        resp = self.conn.parse_response()
        if resp == "Not connected":
            raise ConnectionError("Connection to SkyX succeeded but SkyX reports that it cannot connect to the telescope")

    def check_last_slew_error(self):
        self.conn.send(load_script("check_last_slew_error.js"))
        return self.conn.parse_response()