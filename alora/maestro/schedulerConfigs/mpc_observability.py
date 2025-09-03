import sys, os
from os.path import join, pardir,exists, abspath, dirname
from typing import Union
import astropy.units as u
from alora.maestro.scheduleLib import genUtils
from alora.maestro.schedulerConfigs.MPC_NEO.mpcUtils import MpcEphem, EphemLine
from alora.maestro.scheduleLib.genUtils import timeToString as tts
from alora.astroutils.observing_utils import get_current_sidereal_time, find_transit_time, get_hour_angle, current_dt_utc, dateToSidereal
from alora.astroutils.obs_constraints import ObsConstraint
from astropy.time import Time
import matplotlib.pyplot as plt
from argparse import ArgumentParser

from datetime import datetime, timedelta, timezone

import numpy as np

from time import perf_counter

tmo = ObsConstraint()

def isObservable(ephem_line):
    """
    Is observation described by ephemeris line observable?
    @param ephem: EphemLine
    @return: bool
    """
    # if self.decMin < ephem["dec"] < self.decMax:
    RA, dec = genUtils.ensureAngle(ephem_line.RA), genUtils.ensureAngle(ephem_line.Dec)
    # return self.observationViable(ephem_line.start_dt, RA, dec)
    return genUtils.observation_viable(ephem_line.start_dt,RA,dec)

def determine_observability(ephems:Union[MpcEphem,EphemLine]):
    if isinstance(ephems, MpcEphem):
        raw_ephems = ephems.raw
    else:
        raw_ephems = ephems
    raw_ephems.sort(key=lambda x: x.start_dt)
    obsStart = False
    start = None
    end = None
    for ephem in raw_ephems:
        if isObservable(ephem):
            if not obsStart:  # window begins
                obsStart = True
                start = ephem.start_dt
        elif obsStart:  # we've already started and we're no longer observable. window over
            end = ephem.start_dt
            return (start, end)
        end = ephem.start_dt  # this is the time of the last ephem we could get, so is the 'end' of our window (for now)
    if start is None:  # we've run through all the ephemeris. End the window here, if one was started. otherwise, return None
        # self.logger.info(f"{desig} is not observable at all during the times we have ephemerides for.")
        # ha_start, ha_end = genUtils.getHourAngleLimits(ephems[desig][0].Dec)
        # print(f"RA window: {self.siderealStart + ha_start} to {self.siderealStart + ha_end}")
        # # print(f"current sidereal time: {self.siderealStart}")
        # print(f"RA: {ephems[desig][0].RA}")
        return None
    
    return (start, end)

col_width = 23
label_width = 6
label_gap = 1
col_spacing = 2
line_len = 2 * col_width + col_spacing + label_width + label_gap

        
def ang_to_str(angle):
    return angle.to_string(unit="hourangle",sep=":",precision=1,pad=True)
def col_str(s): return str(s).center(col_width)
def line_str(label, col1, col2):
    return label.rjust(label_width) + " " * label_gap + col_str(col1) + " " * col_spacing + col_str(col2)

def main():
    parser = ArgumentParser()
    parser.add_argument("targets", nargs="+", help="Names of 1 or more targets to process")
    parser.add_argument("--test", default=False, action="store_true", help="Use test ephemerides instead of whatever is in the cache")
    args = parser.parse_args()
    
    if args.test:
        ephem_basedir = join(abspath(dirname(__file__)),"MPC_NEO", "test_ephems")
    else:
        ephem_basedir = join(abspath(dirname(__file__)),"MPC_NEO", "cache", "ephems")

    ephem_names = args.targets
    # ephem_names = ["5HR4J21","P12e56D","P12e56E"]
    for ephem_name in ephem_names:
        print()
        print(f"Observability for target {ephem_name}".center(line_len))
        print("-" * line_len)
        
        ephem_dir = join(ephem_basedir, ephem_name)
        if not exists(ephem_dir):
            print(f"Ephemeris directory not found: {ephem_dir}")
            continue
        
        ephem_files = [f for f in os.listdir(ephem_dir) if f.endswith(".txt")]
        if not len(ephem_files):
            print(f"No ephemeris files found in {ephem_dir}")
            continue
        ephem_files.sort(key = lambda x: int(x.split("_")[1]))
        raw_ephems = []
        for f in ephem_files:
            eph = MpcEphem.from_file(ephem_name,join(ephem_dir,f))
            # print(f"Loaded ephems for {ephem_name} between {tts(eph.start_time)} and {tts(eph.end_time)}")
            raw_ephems.extend(eph.raw)

        joint_eph = MpcEphem(ephem_name,raw_ephems) 

        window = determine_observability(joint_eph)
        if window is None:
            print(f"{ephem_name} is not observable during the available ephemeris ({joint_eph.start_time} to {joint_eph.end_time}).")
            continue

        utcs = []
        local = []
        lsts = []
        HAs = []
        RAs = []
        DECs = []

        local_tz = datetime.now(timezone.utc).astimezone().tzinfo
        local_tz_name = local_tz.tzname(None)

        for t in window:
            eph = joint_eph.get(t)
            utcs.append(tts(t))
            local.append(tts(t.astimezone(local_tz)))
            lsts.append(ang_to_str(Time(t).sidereal_time(longitude=tmo.locationInfo.longitude,kind="apparent")))
            HAs.append(ang_to_str(get_hour_angle(eph.RA,eph.start_dt,tmo.get_obs_lst())))
            RAs.append(ang_to_str(eph.RA))
            DECs.append(ang_to_str(eph.Dec))

        print(line_str("", "Start", "End"))
        print(line_str("UTC:",*utcs))
        print(line_str("Local:", *local))
        print(line_str("HA:",*HAs))
        print(line_str("LST:",*lsts))
        print(line_str("RA:",*RAs))
        print(line_str("DEC:",*DECs))
        print((line_str("EPH:",tts(joint_eph.start_time), tts(joint_eph.end_time))))

if __name__ == "__main__":
    main()

# print((col_str("Start") + col_gap + col_str("End")).rjust(line_len))

# print("UTC:".rjust(label_width))

# print(f"Start Observability: {tts(start_eph.start_dt)} (HA: {start_ha}, RA: {start_eph.RA.to_string(unit='hourangle',sep=':')}, Dec: {start_eph.Dec.to_string(unit='deg',sep=':')})")
# print(f"End Observability: {tts(end_eph.start_dt)} (HA: {end_ha}, RA: {end_eph.RA.to_string(unit='hourangle',sep=':')}, Dec: {end_eph.Dec.to_string(unit='deg',sep=':')})")
# print("approx sidereal:",dateToSidereal(start_eph.start_dt,tmo.get_obs_lst()).wrap_at(360*u.deg).to_string(unit="hourangle",sep=":"))
# obs_time = start_eph.start_dt.replace(microsecond=0)
# print("obs time:",obs_time)
# print(Time(obs_time).sidereal_time(longitude=tmo.locationInfo.longitude,kind="apparent"))
# print(window)

# n = 5000
# offsets = []
# deltas = []
# approxs = []
# directs = []
# offsets = np.random.uniform(-1,1,n) * 1000
# for i in range(n):
#     now = current_dt_utc()
#     current_lst = Time(now).sidereal_time(longitude=tmo.locationInfo.longitude,kind="apparent")
#     target_time = now + timedelta(minutes=offsets[i])
#     direct = Time(target_time).sidereal_time(longitude=tmo.locationInfo.longitude,kind="apparent")
#     approx = dateToSidereal(target_time,current_lst).wrap_at(360*u.deg)
#     print(direct)
#     print(approx)
#     deltas.append((direct - approx).to_value("arcmin"))
#     approxs.append(approx.to_value("arcmin"))
#     directs.append(direct.to_value("arcmin"))



# fig, axes = plt.subplots(nrows=3)



# ax = axes[0]
# ax.scatter(offsets,directs,s=1,alpha=0.75,label="Direct")
# ax.scatter(offsets,approxs,s=1,alpha=0.75,marker="o",label="Approx",color="tab:orange")
# ax.set_ylabel("LST(t)")
# ax.set_xlabel("Target Time - Current Time (minutes)")

# ax = axes[1]


# ax.scatter(np.arange(0,len(deltas),1)[:500],deltas[:500],s=1,alpha=0.75)
# ax.scatter(np.arange(0,len(deltas),1)[-500:],deltas[-500:],s=1,alpha=0.75)
# # ax.set_xlabel("Target Time - Current Time (minutes)")
# # ax.set_ylabel("LST'(t)")

# ax = axes[2]
# ax.scatter(offsets,deltas,s=1,alpha=0.75)
# ax.axvline(0,color="red",linestyle="--")
# ax.axhline(0,color="red",linestyle="--")
# ax.set_xlabel("Target Time - Current Time (minutes)")
# ax.set_ylabel("Approx LST - LST (arcminutes)")

# plt.show()
# # direct calculation average: 0.00125 seconds
# # approximation average: 4.405 * 10^-5 seconds
# durations_direct = []
# sts = []
# for i in range(2000):
#     t = perf_counter()
#     st = Time(obs_time).sidereal_time(longitude=tmo.locationInfo.longitude,kind="apparent")
#     sts.append(st)
#     durations_direct.append(perf_counter()-t)

# durations_approx = []
# lst = tmo.get_obs_lst()
# for i in range(2000):
#     t = perf_counter()
#     st = dateToSidereal(start_eph.start_dt,lst)
#     sts.append(st)
#     durations_approx.append(perf_counter()-t)
# print(sts)
# print()
# print(np.mean(durations_direct),np.median(durations_direct))    
# print()
# print(np.mean(durations_approx),np.median(durations_approx))    
