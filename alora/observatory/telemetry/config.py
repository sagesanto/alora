import os
from os.path import join, dirname, abspath
from alora.config import logging_dir

telem_log_dir = os.path.join(logging_dir,"telemetry")
os.makedirs(telem_log_dir,exist_ok=True)

service_dir = join(dirname(__file__),"services")
os.makedirs(service_dir,exist_ok=True)

fallback_dir = join(dirname(__file__),"fallbacks")
os.makedirs(fallback_dir,exist_ok=True)