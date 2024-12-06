import time
import requests
from bs4 import BeautifulSoup
from alora.observatory.config import get_credential
from alora.observatory.interfaces import Dome

class RelayDome(Dome):
    RELAYS = {"open":1,"close":2}
    TIMINGS_S = {"open":57,"close":57}
    def __init__(self, write_out=print) -> None:
        super().__init__(write_out)
        self.HOSTNAME = get_credential("dome",'addr')
        self.USERNAME = get_credential("dome",'user')
        self.PASSWORD = get_credential("dome",'password')
        self.write_out = write_out
        self.session = requests.Session()

    @property
    def url_template(self):
        return f"http://{self.USERNAME}:{self.PASSWORD}@{self.HOSTNAME}"
    
    def beep(self):
        # run a simple beeper script to warn that the dome is going to move
        _ = self.session.get(self.url_template+f"/script?run001")
        time.sleep(10)

    def status(self):
        r = self.session.get(self.url_template+"/status")
        s = BeautifulSoup(r.content,features="html.parser")
        return s.find_all(attrs={"id":"state"})[0].contents[0]

    def _close(self):
        # DANGER: DO NOT CALL DIRECTLY.
        # Call through observatory object to avoid damaging telescope
        self.beep()
        _ = self.session.get(self.url_template+f"/outlet?{RelayDome.RELAYS['open']}=OFF")
        _ = self.session.get(self.url_template+f"/outlet?{RelayDome.RELAYS['close']}=OFF")
        time.sleep(0.2)
        assert self.status() == "00" 
        _ = self.session.get(self.url_template+f"/outlet?{RelayDome.RELAYS['close']}=ON")
        wait_time = RelayDome.TIMINGS_S['close'] + 10 
        self.write_out(f"Waiting {wait_time} seconds for dome to close")
        time.sleep(wait_time)
        self.write_out("Done!")
        r = self.session.get(self.url_template+f"/outlet?{RelayDome.RELAYS['close']}=OFF")

    def _open(self):
        # DANGER: DO NOT CALL DIRECTLY.
        # Call through observatory object to avoid damaging telescope
        self.beep()
        r = self.session.get(self.url_template+f"/outlet?{RelayDome.RELAYS['close']}=OFF")
        r = self.session.get(self.url_template+f"/outlet?{RelayDome.RELAYS['open']}=OFF")
        time.sleep(0.2)
        assert self.status() == "00" 
        r = self.session.get(self.url_template+f"/outlet?{RelayDome.RELAYS['open']}=ON")
        wait_time = RelayDome.TIMINGS_S['open'] + 10 
        self.write_out(f"Waiting {wait_time} seconds for dome to open")
        time.sleep(wait_time)
        self.write_out("Done!")
        r = self.session.get(self.url_template+f"/outlet?{RelayDome.RELAYS['open']}=OFF")