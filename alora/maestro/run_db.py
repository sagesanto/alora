# Run the database updater directly
import sys, os
import json, logging
import logging.config
import subprocess

MAESTRO_DIR = os.path.abspath((os.path.dirname(__file__)))

path = os.path.join(MAESTRO_DIR,"MaestroCore", "settings.txt")
if not os.path.exists(path):
    path = os.path.join(MAESTRO_DIR,"MaestroCore", "defaultSettings.txt")

# try:
#     with open(os.path.join(MAESTRO_DIR,"logging.json"), 'r') as log_cfg:
#         logging.config.dictConfig(json.load(log_cfg))
#     logger = logging.getLogger(__name__)
#     # set the out logfile to a new path
# except Exception as e:
#     print(f"Can't load logging config ({e}). Using default config.")
#     logger = logging.getLogger(__name__)
#     file_handler = logging.FileHandler(os.path.join(os.path.join(MAESTRO_DIR,"main.log")),mode="a+")
#     logger.addHandler(file_handler)

with open(path, "r") as settingsFile:
    settings = json.load(settingsFile)

settings_dict = {k: v for k, [v, _] in settings.items()}

p = subprocess.Popen([sys.executable, os.path.join("MaestroCore","database.py"), json.dumps(settings_dict)])
