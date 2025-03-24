import os

from .database_SatTest import update_database
from .ephemeris_SatTest import get_ephems
from .schedule_SatTest import getConfig

module_info = "The SatTest module tests satellite observing."
module_contact = "Sage Santomenna (mstp2022@mymail.pomona.edu)"
module_config_file = "sattest_config.txt"


__all__ = ["update_database", "get_ephems", "getConfig", "module_info", "module_contact", "module_config_file"]
# __all__ = [f[:-3] for f in os.listdir() if f[-3:] == ".py" and "init" not in f and not os.path.isdir(f)]