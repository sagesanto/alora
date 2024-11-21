from alora.observatory.dome import Dome
from .observatory import Observatory
try:
    from alora.observatory.skyx import Telescope
except Exception as e:
    print(f"WARNING: unable to import telescope module: {e}")