# import socket
# s = socket.socket()
# s.connect(("localhost", 3040))
# s.send(b"""/* Java Script */
# /* Socket Start Packet */

# var Out;
# sky6RASCOMTele.Connect();

# if (sky6RASCOMTele.IsConnected==0)/*Connect failed for some reason*/
# {
# 	Out = "Not connected"
# }
# else
# {
# 	sky6RASCOMTele.GetRaDec();
# 	Out  = String(sky6RASCOMTele.dRa) +"| " String(sky6RASCOMTele.dDec);
# }

# /* Socket End Packet */""")
# # filetosend = open("img.png", "rb")
# # data = filetosend.read(1024)
# # while data:
# #     print("Sending...")
# #     s.send(data)
# #     data = filetosend.read(1024)
# # filetosend.close()

# # s.send(b"DONE")
# print("Done Sending.")
# print(s.recv(1024))
# s.shutdown(2)
# s.close()
# #Done :)

from os.path import join
import socket
import tomlkit
import astropy.units as u
from astropy.coordinates import SkyCoord

from . import js_script_path
from alora.observatory.config import config_path

def load_script(script_name):
    with open(join(js_script_path,script_name)) as f:
        return "\n".join(f.readlines())

with open(config_path,"rb") as f:
    config = tomlkit.load(f)

class SkyXClient:
    HEADER = "\* Java Script *\ "
    def __init__(self,port):
        self.port = port
        self.socket = socket.socket()
        self.socket.connect(("localhost", port))
        self.test_conn()
    
    def send(self,content):
        print(content)
        self.socket.send((SkyXClient.HEADER+"\n"+content).encode())

    def test_conn(self):
        script = load_script("check_tel_conn.js")
        self.send(script)
        # self.socket.send(b"""/* Java Script */
        #     var Out;
        #     sky6RASCOMTele.Connect();
        #     Out = sky6RASCOMTele.IsConnected; 

        #     if (sky6RASCOMTele.IsConnected==0)/*Connect failed for some reason*/
        #     {
        #         Out = "Not connected"
        #     }
        #     else
        #     {
        #         sky6RASCOMTele.GetRaDec();
        #         Out  = String(sky6RASCOMTele.dRa) +" " + String(sky6RASCOMTele.dDec);
        #     }
        # """)
        r, error = self.parse_response()
        if error:
            raise ConnectionError(f"Connection to SkyX failed. Response was {r} | {error}")
        if r == "0":
            raise ConnectionError(f"SkyX reports that it cannot connect to the telescope.")
        print(f"Connected to TheSkyX on port {self.port}.")

    def parse_response(self,rlen=1024):
        response = self.socket.recv(rlen).decode('UTF-8')
        if response is None:
            return None, 1
        content, error = response.split("|")
        if error == "No error. Error = 0.":
            error = 0
        return content.strip(), error

conn = SkyXClient(config["SKYX_PORT"])

class Telescope:
    def __init__(self):
        self.conn = conn
        self.check_pos_script = load_script("get_telescope_pos.js")
    
    @property
    def pos(self):
        self.conn.send(self.check_pos_script)
        resp, error = self.conn.parse_response()
        if error or resp == "Not connected":
            raise ConnectionError(f"Unable to get telescope position. Response was {resp} | {error}")
        ra, dec = resp.split(" ")
        ra = float(ra)
        dec = float(dec)
        return SkyCoord(ra=ra*u.deg,dec=dec*u.deg)