from os.path import abspath, dirname, join
import tomlkit
dir = dirname(abspath(__file__))

config_path = join(dir, "config.toml")
logging_config_path = join(dir, "logging.json")

with open(config_path,"rb") as f:
    config = tomlkit.load(f)

from .utils import configure_logger