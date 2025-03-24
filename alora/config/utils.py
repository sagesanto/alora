import os
import json
import logging
import keyring
from pathlib import Path
import logging.config
from os.path import join, dirname, abspath, pardir
import tomlkit
from typing import List, Any

from alora.config import logging_config_path

def configure_logger(name, outfile_path=None):
    # first, check if the logger has already been configured
    if logging.getLogger(name).hasHandlers():
        return logging.getLogger(name)
    try:
        with open(logging_config_path, 'r') as log_cfg:
            logging.config.dictConfig(json.load(log_cfg))
            logger = logging.getLogger(name)
            # set outfile of existing filehandler. need to do this instead of making a new handler in order to not wipe the formatter off
            # NOTE RELIES ON FILE HANDLER BEING THE SECOND HANDLER
            root_logger = logging.getLogger()
            if outfile_path is not None:
                file_handler = root_logger.handlers[1]
                file_handler.setStream(Path(outfile_path).open('a'))
            else:
                # remove the file handler
                root_logger.removeHandler(root_logger.handlers[1])
            try:
                os.remove("should_be_set_by_code.log")  # pardon this
            except:
                pass

    except Exception as e:
        print(f"Can't load logging config ({e}). Using default config.")
        logger = logging.getLogger(name)
        if outfile_path is not None:
            file_handler = logging.FileHandler(outfile_path, mode="a+")
            logger.addHandler(file_handler)

    # install_mp_handler()
    return logger

def get_credential(cred_name,username):
    p = keyring.get_password(cred_name,username)
    if p is None:
        raise ValueError(f"Missing credential for service '{cred_name}' with username '{username}'! Please consult {abspath(join(dirname(__file__),pardir,'credentials.md'))}")
    return p


def _read_config(config_path:str):
    with open(config_path, "rb") as f:
        cfg = tomlkit.load(f)
    return cfg

class Config:
    def __init__(self,filepath:str,default_path:str|None=None,default_env_key:str="CONFIG_DEFAULTS"):
        """Create a config object from a toml file. Optionally, add a fallback default toml config, read from `default_path`. If `default_path` is `None`, will also check the CONFIG_DEFAULTS environment varaible for a defaults filepath. 

        Profiles (toml tables) can be selected with :func:`Config.choose_profile` and deselected with :func:`Config.clear_profile`. Keys in a profile will take precedence over keys in the rest of the file and in the defaults file.
        If `"KEY"` is in both the standard config and the profile `"Profile1"`::
        
        >>> cfg = Config("config.toml",default_path="defaults.toml")
        >>> cfg["KEY"] # VAL1 
        >>> cfg.select_profile("Profile1")
        >>> cfg["KEY"] # VAL2

        If `"KEY"` is only in both the standard config::
        >>> cfg["KEY"] # VAL1 
        >>> cfg.select_profile("Profile1")
        >>> cfg["KEY"] # VAL1

        Values can be retrieved in a few ways:: 
        
        >>> # the following are equivalent:
        >>> cfg["KEY"]
        >>> cfg("KEY")
        >>> # this allows a default value in case the key can't be found in a profile, main config, or default:
        >>> cfg.get("KEY")  # will return None if not found
        >>> cfg.get("KEY","Not found") # returns 'Not found' if not found
        >>> # this queries the default config for a key. will fail if a default config is not set:
        >>> cfg.get_default("KEY")
        
        Values can also be set. Setting a key that doesn't currently exist will add it to the config. Setting a key will change the state of the object but will not change the file unless :func:`Config.save()` is called::

        >>> cfg["KEY"] = "VALUE"  # sets in selected profile, or in main config if no profile selected
        >>> cfg["table"]["colnames"] = ["ra","dec"]  # can do nested set
        >>> cfg.set("KEY") = "VALUE"  # sets in selected profile, or in main config if no profile selected
        >>> cfg.set("KEY", profile=False) = "VALUE"  # sets in main profile, ignoring selected profile

        Can write the whole config (not just the profile, and not including the defaults) into the given file::
        
        >>> cfg.write("test.toml")
        
        Or can write to the file the config was loaded from, overwriting previous contents (does not modify defaults file)::

        >>> cfg.save()
         
        :param filepath: toml file to load config from
        :type filepath: str
        :param default_path: default toml file to load defaults from, defaults to None
        :type default_path: str | None, optional
        :param default_env_key: will load defaults from here if this is set and default_path is not provided, defaults to `"CONFIG_DEFAULTS"`
        :type default_env_key: str, optional
        """
        self._cfg = _read_config(filepath)
        self.selected_profile = None
        self._defaults = None
        self._filepath = filepath 
        self.selected_profile_name = None
        self._default_path = default_path
        if not self._default_path:
            self._default_path = os.getenv(default_env_key)
        if self._default_path:
            try:
                self._defaults = _read_config(self._default_path)
            except Exception as e:
                print(f"ERROR: config tried to load defaults file {self._default_path} but encountered the following: {e}")
                print("Proceeding without defaults")

    def choose_profile(self, profile_name:str):
        self.selected_profile = self._cfg[profile_name]
        self.selected_profile_name = profile_name
        return self
    
    def clear_profile(self):
        self.selected_profile = None
        self.selected_profile_name = None
    
    def load_defaults(self, filepath:str):
        self._defaults = _read_config(filepath)
        self._default_path = filepath

    def write(self,fpath,trim=True):
        """Writes the whole config loaded from file (not just the profile, and not including the defaults) into the given file"""
        with open(fpath,"w") as f:
            outstr = tomlkit.dumps(self._cfg)
            if trim:
                outstr = outstr.replace("\r\n","\n")
            f.write(outstr)
    
    def save(self,trim=True):
        """Saves the whole config loaded from file (not just the profile, and not including the defaults) into the file it was loaded from"""
        self.write(self._filepath,trim=trim)

    @property
    def has_defaults(self):
        return self._defaults is not None
    
    def _get_default(self, key:str):
        if not self.has_defaults:
            raise AttributeError("No default configuration set!")
        return self._defaults[key]

    def get_default(self, key:str, default:Any|None=None):
        try: 
            self._get_default(key)
        except KeyError:
            return default
    
    def get(self,key:str,default:Any=None):
        try:
            return self.__getitem__(key)
        except KeyError:
            return default

    def set(self,key:str,value:Any,profile:bool=True):
        if profile:
            self[key] = value
            return
        else:
            self._cfg[key] = value

    def __call__(self, index:str) -> Any:
        return self.__getitem__(index)

    def __getitem__(self,index:str) -> Any:
        if self.selected_profile:
            try:
                return self.selected_profile[index]
            except Exception:
                pass
        try:
            return self._cfg[index]    
        except Exception:
            if self.has_defaults:
                return self._get_default(index)
            raise KeyError(f"Key '{index}' not found in config {self._filepath}" + (f"or defaults {self._default_path}" if self.has_defaults else ""))
        
    def __setitem__(self,index:str,new_val:Any) -> Any:
        if self.selected_profile:
                self.selected_profile[index] = new_val
                return
        self._cfg[index] = new_val
    
    def __str__(self):
        self_str = ""
        if self.selected_profile:
            self_str = f"(Profile '{self.selected_profile_name}') "
        
        self_str += str(self._cfg)
        if self.has_defaults:
            self_str += f"\nDefaults: {self._defaults}"
        return self_str

    def __repr__(self) -> str:
        return f"Config from {self._filepath} with {f'profile {self.selected_profile_name}' if self.selected_profile_name else 'no profile'} selected and {f'defaults loaded from {self._default_path}' if self.has_defaults else 'no defaults loaded'}"
