import os
import requests, socketio
import threading
from astropy.coordinates import SkyCoord, Angle
import astropy.units as u
from alora.astroutils.obs_constraints import ObsConstraint

from alora.config import config, logging_dir, configure_logger

logger = configure_logger(os.path.join(logging_dir, "observing_client.log"))  # will want to not have a dedicated global logger for all obs clients in the future


class Observatory(ObsConstraint):
    def __init__(self,write_out=print) -> None:
        super().__init__()
        self.PORT = config["OBSERVER"]["PORT"]
        self.URL = f"http://localhost:{self.PORT}"
        self.session = requests.Session()
        self.sio = socketio.Client()
        self.sio.connect(self.URL)
        self.write_out = write_out

    def _send_event(self,event_name,client,priority,args,wait=False):
        r = self.session.post(f"{self.URL}/exec/{event_name}",json={"client":client,"priority":priority,"args":args})
        self.write_out(f"Sent event {event_name}")
        if r.status_code != 200:
            self.write_out(f"Unsuccessful request (status code: {r.status_code})")
            self.write_out(r.content)
            return
        event_id = r.json()["event_id"]
        self.write_out(f"Event {event_id} created.")
        if wait:
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

    def slew(self, coord:SkyCoord, closed_loop=True,closed_exptime=1):
        self._send_event("Slew","test","normal",{"ra":{"ra":coord.ra.deg,"unit":"deg"},"dec":{"dec":coord.dec.deg,"unit":"deg"}, "closed_loop":closed_loop,"closed_exptime":{"closed_exptime":closed_exptime,"unit":"second"}},wait=True)

def write_out(*args):
    logger.info(" ".join(args))    

obs = Observatory(write_out=write_out)
lst = obs.get_obs_lst()

obs.slew(SkyCoord(ra=lst,dec=0*u.deg),closed_loop=True,closed_exptime=1)

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