import os

from .database_Astrophotography import update_database
from .ephemeris_Astrophotography import get_ephems
from .schedule_Astrophotography import scheduling_config
from .candidate_Astrophotography import AphotCandidate as CandidateClass

module_path = os.path.dirname(os.path.realpath(__file__))

# module_name = "Astrophotography"
# module_info = "The astrophotography (\"aphot\") module presents photogenic astronomical objects as targets of last resort. These targets are not populated in the database."
# module_contact = "Sage Santomenna (mstp2022@mymail.pomona.edu)"
# module_config_file = os.path.join(module_path, "aphot_config.json")
# module_config_header = "DEFAULT"

__all__ = ["update_database", "get_ephems", "scheduling_config", "CandidateClass"] # __all__ = [f[:-3] for f in os.listdir() if f[-3:] == ".py" and "init" not in f and not os.path.isdir(f)]
# __all__ = ["update_database", "get_ephems", "getConfig", "module_info", "module_contact", "module_config_file", "module_name", "module_config_header", "ClassCandidate"] # __all__ = [f[:-3] for f in os.listdir() if f[-3:] == ".py" and "init" not in f and not os.path.isdir(f)]