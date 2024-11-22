from os.path import abspath, dirname, join
dir = dirname(abspath(__file__))

config_path = join(dir, "config.toml")
logging_config_path = join(dir, "logging.json")

from .utils import configure_logger