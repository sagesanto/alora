import os, shutil, glob
from os.path import abspath, dirname, join, exists, pardir
import tomlkit
dir = dirname(abspath(__file__))

config_path = join(dir, "config.toml")
logging_config_path = join(dir, "logging.json")
horizon_box_path = join(dir, "horizon_box.json")

logging_dir = abspath(join(dir,pardir,"logs"))
os.makedirs(logging_dir,exist_ok=True)

maestro_cfg_dir = abspath(join(dir,pardir,"maestro","files","configs"))
config_dirs = [dir, maestro_cfg_dir]

# recursively search for dirs containing ".default" files
config_dirs = set([dirname(abspath(f)) for f in glob.glob(join(dir,pardir,"**","*.default"),recursive=True)])
print("Found .default files in the following dirs:", ", ".join(config_dirs))
for d in config_dirs:
    for f in [f for f in os.listdir(d) if ".default" in f]:
        active = join(d,f.replace(".default",""))
        if not exists(active):
            shutil.copy(join(d,f),active)
        elif active.endswith("toml"):
            with open(join(d,f),"rb") as default:
                default_cfg = tomlkit.load(default)
            with open(active,"rb") as ac:
                active_cfg = tomlkit.load(ac)
            def update_cfg(default, active,path="",paths=[]):
                for k, v in default.items():
                    if k not in active:
                        active[k] = v
                        paths.append(path + k)
                        # print("added key",path+k)
                    elif isinstance(v, dict):
                        paths = update_cfg(v, active[k],path+k+".",paths)
                return paths
            key_paths = update_cfg(default_cfg,active_cfg)
            if key_paths:
                with open(active,"w") as f:
                    f.write(tomlkit.dumps(active_cfg).replace("\r\n","\n"))
                from .utils import configure_logger
                logger = configure_logger("config",join(logging_dir,'config.log'))
                logger.warn(f"[ALORA] The default config '{join(d,f)}' has new keys that were not present in the active config '{active}'. Default values were copied over for the following new keys: {key_paths}")
                # raise ValueError(f"[ALORA] The config template '{join(d,f)}' has new keys that are not present in the active config '{active}'. Please provide values for the following new keys: {key_paths}")

with open(config_path,"rb") as f:
    config = tomlkit.load(f)

default_binning = config["DEFAULTS"]["BIN"]


from astral import LocationInfo

obs_cfg = config["OBSERVATORY"] 
observatory_location = LocationInfo(name=obs_cfg["NAME"], region=obs_cfg["REGION"],
                                timezone=obs_cfg["TIMEZONE"],
                                latitude=obs_cfg["LATITUDE"],
                                longitude=obs_cfg["LONGITUDE"])