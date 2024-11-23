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

def run_watchdog(address_to_monitor,port):
    o = Observatory(write_out=write_out)

    DROP_LIMIT = 3

    dropped = 0
    write_out(f"Watching for internet dropouts ({address_to_monitor}:{port})...")
    while True:
        r = ping(address_to_monitor,port)
        if not r:
            dropped += 1
            if dropped <= DROP_LIMIT:
                write_out(f"Dropped a connection! Consecutive drops: {dropped}")
        else:
            if dropped >= DROP_LIMIT:
                write_out("Connection regained.")
            dropped = 0
        if dropped == 3:  # == instead of >= prevents us from repeatedly closing the dome
            write_out("CLOSING DUE TO DROPPED CONNECTION")
            o.close()
            write_out("Waiting for internet connection...")
        time.sleep(1)

if __name__ == "__main__":
    run_watchdog("google.com",80)