import os
import requests, socketio
import threading
from astropy.coordinates import SkyCoord, Angle
import astropy.units as u
from enum import Enum
import time

from alora.astroutils.obs_constraints import ObsConstraint
from alora.config import config, logging_dir, configure_logger

logger = configure_logger(os.path.join(logging_dir, "observing_client.log"))  # will want to not have a dedicated global logger for all obs clients in the future

class Priority(Enum):
    LOW = "low"
    NORMAL = "normal"
    CRITICAL = "critical"


class Observatory:
    def __init__(self,client_name,write_out=print,priority:Priority=Priority.NORMAL, synchronous = True) -> None:
        self.PORT = config["OBSERVER"]["PORT"]
        self.URL = f"http://localhost:{self.PORT}"
        self.session = requests.Session()
        self.sio = socketio.Client()
        self.sio.connect(self.URL)
        self.write_out = write_out
        self.synchronous = synchronous
        self.priority = priority
        self.client_name = client_name
        self.physical = ObsConstraint()

    def _send_event(self,event_name,args=None,client_name=None,priority:Priority|None=None,synchronous=None):
        args = args or {}
        client_name = client_name  or self.client_name
        priority = priority or self.priority
        synchronous = synchronous if synchronous is not None else self.synchronous
        self.write_out(priority.value, type(priority.value))
        self.write_out("Args: ",args)
        r = self.session.post(f"{self.URL}/exec/{event_name}",json={"client":client_name,"priority":priority.value,"args":args})
        self.write_out(f"Sent event {event_name}")
        if r.status_code != 200:
            self.write_out(f"Unsuccessful request (status code: {r.status_code})")
            self.write_out(r.content)
            return
        event_id = r.json()["event_id"]
        self.write_out(f"Event {event_id} created.")
        if synchronous:
            self.write_out("Waiting for event to finish...")
            event_done_event = threading.Event()
            @self.sio.on("event_finished")
            def event_finished(data):
                self.write_out(f"Got event finished: {data}")
                if data["event_id"] == event_id:
                    self.write_out(f"Event {event_id} done. Status: {data['status']}")
                    self.sio.disconnect()
                    event_done_event.set()
                else:
                    self.write_out(f"Got event-finished for event {data['event_id']}, but waiting for event {event_id}")
            event_done_event.wait()
            self.sio.connect(self.URL)
            self.write_out("Event done.")

    def wait(self,duration,**kwargs):
        self._send_event("Wait",{"duration":duration},**kwargs)

    def slew(self, coord:SkyCoord, closed_loop=True,closed_exptime=1, **kwargs):
        self._send_event("Slew",{"ra":{"ra":coord.ra.deg,"unit":"deg"},"dec":{"dec":coord.dec.deg,"unit":"deg"}, "closed_loop":closed_loop,"closed_exptime":{"closed_exptime":closed_exptime,"unit":"second"}}, **kwargs)

    def close(self, **kwargs):
        self._send_event("CloseSequence", **kwargs)

    def open(self,do_home=False, **kwargs):
        self._send_event("OpenSequence",{"do_home":do_home}, **kwargs) 

    def home(self, **kwargs):
        self._send_event("Home", **kwargs)

    def park(self, **kwargs):
        self._send_event("Park", **kwargs)

    def shutdown(self, **kwargs):
        self._send_event("Shutdown", **kwargs)

    def reactivate(self, **kwargs):
        self._send_event("Reactivate", **kwargs)

    def reserve(self, **kwargs):
        self._send_event("Reserve", **kwargs)

    def free(self, **kwargs):
        self._send_event("Free", **kwargs)

    def lockdown(self):
        self._send_event("ForceCloseSequence", priority=Priority.CRITICAL, synchronous=False)
        self.shutdown(priority=Priority.CRITICAL)


def write_out(*args):
    logger.info(" ".join([str(a) for a in args]))    

if __name__ == "__main__":  
    # print(config)
    # print(config["OBSERVER"])
    obs = Observatory("test",write_out=write_out,synchronous=False)
    # lst = obs.physical.get_obs_lst()

    obs.wait(20)
    time.sleep(1)
    obs.wait(5,priority=Priority.CRITICAL)

    # obs.close()
    # # obs.reactivate()
    # obs.open()
    # obs.close()
    # # obs.lockdown()
    # # obs.open()  # should fail if after lockdown
    # # obs.reactivate()
    # # obs.open(synchronous=True)
    # # obs.home()
    # # obs.park()
    # # obs.close()

# obs.slew(SkyCoord(ra=lst,dec=0*u.deg),closed_loop=True,closed_exptime=2)



# endpoints = {"s":"Shutdown","u":"Reactivate","r":"Reserve","f":"Free"}

## this tests that the observatory can change state appropriately
# while True:
#     i = input("Type 's' to shutdown the observatory, 'u' to reactivate it, 'r' to reserve it, or 'f' to free it: ")
#     print(requests.post(f"{URL}/exec/{endpoints[i]}",json={"client":"test","priority":"normal","args":{}}).content)


# send_event("Wait","test","low",{"duration":10},wait=True)
# send_event("Slew","test","normal",{"ra":{"ra":0,"unit":"deg"},"dec":{"dec":0,"unit":"deg"}},wait=True)

# this tests that the observatory prioritizes events correctly (look at state page to see queue sizes in realtime)
# for i in range(5):
#     print(requests.post(f"{URL}/exec/Wait",json={"client":"test","priority":"low","args":{"duration":10}}).content)
#     print(requests.post(f"{URL}/exec/Wait",json={"client":"test","priority":"normal","args":{"duration":10}}))

# print(requests.post(f"{URL}/exec/Wait",json={"client":"test","priority":"critical","args":{"duration":10}}))