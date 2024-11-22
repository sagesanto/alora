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

class Telescope:
    def __init__(self, write_out=print):
        self.write_out = write_out
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
        return SkyCoord(ra=ra*u.deg,dec=dec*u.deg)
    
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
        return self.conn.connected and self.test_mount_conn()

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