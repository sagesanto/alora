import sys, os
import requests

from alora.observatory.config import config

class Vocalist:
    def __init__(self,name):
        self.name = name
        self.session = requests.Session()

    def notify(self,severity,topic,msg,source="self"):
        if source == "self":
            source = self.name
        r = self.session.post(f"http://127.0.0.1:{config['CHOIR_PORT']}/notify",json={"source":source,"severity":severity,"topic":topic,"msg":msg},headers={"Content-Type":"application/json"})
        if r.status_code >= 400:
            raise ValueError(f"Failed to notify: error code '{r.status_code}'. Response text was '{r.content}'")
        j = r.json()
        status = r.json()["status"]
        if status != "success":
            raise ValueError(f"Failed to notify: status '{status}'. Error text was '{j['message']}'")
        return r.content

    def info(self,topic,msg,source="self"):
        return self.notify("info",topic,msg,source)
    
    def warning(self,topic,msg,source="self"):
        return self.notify("warning",topic,msg,source)
    
    def error(self,topic,msg,source="self"):
        return self.notify("error",topic,msg,source)
    
    def critical(self,topic,msg,source="self"):
        return self.notify("critical",topic,msg,source)

if __name__ == "__main__":
    v = Vocalist("Vocalist/Choir notification test")
    # print(v.info("test","hi"))
    # print(v.warning("test","hi"))
    # print(v.error("test","hi"))
    print(v.critical("Test","Test of the Vocalist/Choir notification system"))
    # print(v.notify("info","test","hi"))
    # print(v.notify("test2","test","this should fail"))