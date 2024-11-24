from alora.observatory.config import config

class Observation:
    def __init__(self, coord, obs_time, exp_time_s, nframes, filter, track_rates="sidereal", closed_loop=False, exp_delay=0, binning=config["DEFAULTS"]["BIN"]):
        self.coord = coord
        self.obs_time = obs_time
        self.exp_time_s = exp_time_s
        self.nframes = nframes
        self.filter = filter
        self.track_rates = track_rates
        self.closed_loop = closed_loop
        self.exp_delay = exp_delay
        self.binning = binning