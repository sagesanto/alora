import os

from .database_Astrophotography import update_database
from .ephemeris_Astrophotography import get_ephems
from .schedule_Astrophotography import getConfig

module_info = "The astrophotography (\"aphot\") module presents photogenic astronomical objects as targets of last resort. These targets are not populated in the database."
module_contact = "Sage Santomenna (mstp2022@mymail.pomona.edu)"
module_config_file = "aphot_config.txt"


__all__ = ["update_database", "get_ephems", "getConfig", "module_info", "module_contact", "module_config_file"]
# __all__ = [f[:-3] for f in os.listdir() if f[-3:] == ".py" and "init" not in f and not os.path.isdir(f)]