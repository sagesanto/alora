import pandas as pd
import numpy as np

# calculate the number of frames of duration exptime to fill an observation 
def calc_num_frames(start_obs, end_obs, exptime):
    if not start_obs or not end_obs or pd.isnull(start_obs) or pd.isnull(end_obs):
        return -1
    return int(np.ceil((end_obs - start_obs).total_seconds() / exptime)) # - 5*int(np.ceil(60/exptime)) # need to subtract off for scheduler reasons
