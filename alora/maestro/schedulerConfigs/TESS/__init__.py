import os

from .database_TESS import update_database
from .ephemeris_TESS import get_ephems
from .schedule_TESS import scheduling_config
from .candidate_TESS import TESSCandidate as CandidateClass


module_path = os.path.dirname(os.path.realpath(__file__))

# module_name = "TESS"
# module_info = "The TESS module is designed for observations of CSV-specified exoplanet-candidate transits. It does NOT support general-purpose TESS observations." 
# module_contact = "Sage Santomenna (mstp2022@mymail.pomona.edu), Pei Qin (pqaa2018@pomona.edu)"
# module_config_file = os.path.join(module_path, "tess_config.json")
# module_config_header = "DEFAULT"

__all__ = ["update_database", "get_ephems", "scheduling_config"]
# __all__ = ["update_database", "get_ephems", "getConfig", "module_info", "module_contact", "module_config_file", "module_name", "module_config_header"]