import os
from os.path import dirname, join
from alora.observatory.observatory import Observatory
import socket
import time
from alora.observatory.config import configure_logger

# from https://stackoverflow.com/a/67217558
def ping(server: str, port: int, timeout=3):
    """ping server"""
    try:
        socket.setdefaulttimeout(timeout)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((server, port))
    except OSError as error:
        return False
    else:
        s.close()
        return True

logpath = join(dirname(__file__),'watchdog.log')
logger = configure_logger("watchdog",outfile_path=logpath)

def write_out(*args,**kwargs):
    logger.info(" ".join([str(a) for a in args]))

o = Observatory(write_out=write_out)

dropped = 0
write_out("Watching for internet dropouts...")
while True:
    r = ping("google.com",80)
    if not r:
        dropped += 1
        write_out(f"Dropped a connection! Consecutive drops: {dropped}")
    else:
        dropped = 0
    if dropped == 3:
        write_out("CLOSING DUE TO DROPPED CONNECTION")
        o.close()
    time.sleep(1)