import os
from .database_UserFixed import update_database
from .ephemeris_UserFixed import get_ephems
from .schedule_UserFixed import getConfig

module_info = "The UserFixed module is designed to be an easy default for observations of user-specified static targets. Targets added by CSV with the CandidateType 'UserFixed' will be governed by this module." 
module_contact = "Sage Santomenna (mstp2022@mymail.pomona.edu)"
module_config_file = "userFixed_config.txt"

__all__ = ["update_database", "get_ephems", "getConfig", "module_info", "module_contact", "module_config_file"]