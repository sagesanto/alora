import time
import requests
from bs4 import BeautifulSoup

class Dome:
    RELAYS = {"open":1,"close":2}
    TIMINGS_S = {"open":57,"close":57}
    def __init__(self,ip_addr,username,password) -> None:
        self.HOSTNAME = ip_addr
        self.USERNAME = username
        self.PASSWORD = password
        self.session = requests.Session()

    @property
    def url_template(self):
        return f"http://{self.USERNAME}:{self.PASSWORD}@{self.HOSTNAME}"
    
    def status(self):
        r = self.session.get(self.url_template+"/status")
        s = BeautifulSoup(r.content)
        print(s.find_all(attrs={"id":"state"}))
        print(s.find_all(attrs={"id":"state"})[0])
        print(s.find_all(attrs={"id":"state"})[0].contents[0])
        return s.find_all(attrs={"id":"state"})[0].contents[0]
    
    def close(self):
        _ = self.session.get(self.url_template+f"/outlet?{Dome.RELAYS['open']}=OFF")
        _ = self.session.get(self.url_template+f"/outlet?{Dome.RELAYS['close']}=OFF")
        time.sleep(0.2)
        assert self.status() == "00" 
        _ = self.session.get(self.url_template+f"/outlet?{Dome.RELAYS['close']}=ON")
        wait_time = Dome.TIMINGS_S['close'] + 10 
        print(f"Waiting {wait_time} seconds for dome to close")
        time.sleep(wait_time)
        print("Done!")
        r = self.session.get(self.url_template+f"/outlet?{Dome.RELAYS['close']}=OFF")

    def open(self):
        r = self.session.get(self.url_template+f"/outlet?{Dome.RELAYS['close']}=OFF")
        r = self.session.get(self.url_template+f"/outlet?{Dome.RELAYS['open']}=OFF")
        time.sleep(0.2)
        assert self.status() == "00" 
        r = self.session.get(self.url_template+f"/outlet?{Dome.RELAYS['open']}=ON")
        wait_time = Dome.TIMINGS_S['open'] + 10 
        print(f"Waiting {wait_time} seconds for dome to open")
        time.sleep(wait_time)
        print("Done!")
        r = self.session.get(self.url_template+f"/outlet?{Dome.RELAYS['open']}=OFF")