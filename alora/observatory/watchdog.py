from alora.observatory.observatory import Observatory
import socket
import time

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
    
o = Observatory()
dropped = 0
while True:
    r = ping("google.com",80)
    if not r:
        dropped += 1
    else:
        dropped = 0
    if dropped == 3:
        print("CLOSING DUE TO DROPPED CONNECTION")
        o.close()
    time.sleep(1)