import sys, os
from os.path import exists, abspath
from datetime import datetime

from sagelib.pipeline import Pipeline, Product, configure_db
from sagelib.utils import current_dt_utc

from sagelib.pipeline.bin.create_db import main as create_db  # cringe and fail

from alora.config import config, config_path

def write_out(*args):
    print(*args)

class Archive:
    def __init__(self,fpath):
        if not exists(fpath):
            write_out(f"No archive found at {fpath}. Creating one...")
            create_db(fpath)
        self.fpath = fpath
        self.session, _ = configure_db(fpath)
        self.pipeline = Pipeline("Archiver",[],".",config_path,"0.0",dbpath=fpath)
    
    def create_product(self,data_type: str, creation_dt:datetime, product_location:str, flags:int | None=None, data_subtype: str | None=None, **kwargs):
        p = self.pipeline.product(data_type, creation_dt, product_location, flags, data_subtype, **kwargs)
        return p
    
    def find_products(self,data_type: str, metadata:None|dict=None, **filters):
        pass

a = Archive(abspath("./test_archive.db"))
p = a.create_product("test_input", current_dt_utc(),"test_input loc")
print(p)
# class Observation:
#     def __init__(self, coord, obs_time, exp_time_s, nframes, filter, track_rates="sidereal", closed_loop=False, exp_delay=0, binning=config["DEFAULTS"]["BIN"]):
#         self.coord = coord
#         self.obs_time = obs_time
#         self.exp_time_s = exp_time_s
#         self.nframes = nframes
#         self.filter = filter
#         self.track_rates = track_rates
#         self.closed_loop = closed_loop
#         self.exp_delay = exp_delay
#         self.binning = binning