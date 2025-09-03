from os.path import join
from astropy.coordinates import Angle
import matplotlib.pyplot as plt

from alora.astroutils.obs_constraints import ObsConstraint
from alora.astroutils.observing_utils import get_current_sidereal_time, find_transit_time, get_hour_angle, current_dt_utc



if __name__ == "__main__":
    class Candidate:
        def __init__(self,RA:Angle, Dec, CandidateName):
            self.RA = RA 
            self.Dec = Dec
            self.CandidateName = CandidateName

    tmo = ObsConstraint()
    lst = get_current_sidereal_time(tmo.locationInfo)
    t = find_transit_time(lst,tmo.locationInfo)
    print("Current time:",current_dt_utc())
    print("Hour angle:",get_hour_angle(lst,t,lst))
    print("Transit time:", find_transit_time(RA=lst,location=tmo.locationInfo,target_dt=t))
    c = [Candidate(**{"RA":lst,"Dec":0,'CandidateName':"test"})]
    # t = find_transit_time(c[0].RA,tmo.locationInfo) + timedelta(hours=1.5)
    tmo.plot_onsky(candidates=c,dt=t)
    print("Observable:",tmo.observation_viable(t,lst,0, ignore_night=True))
    plt.show()