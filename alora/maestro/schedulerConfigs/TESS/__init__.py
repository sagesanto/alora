import os

from .database_TESS import update_database
from .ephemeris_TESS import get_ephems
from .schedule_TESS import getConfig

module_info = "The TESS module is designed for observations of CSV-specified exoplanet-candidate transits. It does NOT support general-purpose TESS observations." 
module_contact = "Pei Qin (pqaa2018@pomona.edu)"
module_config_file = "tess_config.txt"

__all__ = ["update_database", "get_ephems", "getConfig", "module_info", "module_contact", "module_config_file"]