import os
from os.path import abspath, dirname, join
import tomlkit
dir = dirname(abspath(__file__))

config_path = join(dir, "config.toml")
logging_config_path = join(dir, "logging.json")

logging_dir = abspath(join(dir,os.pardir,"logs"))
os.makedirs(logging_dir,exist_ok=True)

with open(config_path,"rb") as f:
    config = tomlkit.load(f)

default_binning = config["DEFAULTS"]["BIN"]

from .utils import configure_logger, get_credential