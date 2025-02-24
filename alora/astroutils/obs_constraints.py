# Sage Santomenna 2024
# observability utilities. relies on observing_utils.py

import os
import json
from .observing_utils import get_angle, get_centroid, get_current_sidereal_time, dateToSidereal, find_transit_time, get_sunrise_sunset, get_hour_angle, angleToTimedelta, ensureFloat, ensureAngle, wrap_around, sidereal_rate, current_dt_utc
import pytz, time
from datetime import datetime, timedelta, timezone
from astral import sun, LocationInfo
from astropy.coordinates import Angle
from astropy.table import Table, QTable
import astropy.units as u
import matplotlib.pyplot as plt, numpy as np
import logging
from alora.config import config, observatory_location, horizon_box_path

obs_cfg = config["OBSERVATORY"]

BBOX_BUFFER_DEG = obs_cfg["BBOX_BUFFER_DEG"]

with open(horizon_box_path, "r") as f:
    data = json.load(f)
HORIZON_BOX = {}
for i in np.arange(len(data),step=2):
    HORIZON_BOX[tuple(data[i])] = tuple(data[i+1])

def sign(num):
    return 0 if num == 0 else num/abs(num)

# ugly - shrink the bbox by BBOX_BUFFER_DEG
HORIZON_BOX_2 = HORIZON_BOX.copy()
for k,v in HORIZON_BOX.items():
    v1 = (sign(v[0]) * (abs(v[0])-BBOX_BUFFER_DEG), sign(v[1]) * (abs(v[1])-BBOX_BUFFER_DEG))
    HORIZON_BOX_2[k] = v1
HORIZON_BOX = HORIZON_BOX_2

# flip the sign of the HA (second tuple) and their order in HORIZON_BOX to represent flipping the telescope
FLIPPED_BOX = {k:(-v[1],-v[0]) for k,v in HORIZON_BOX.items()}
# print(FLIP_BOX)

_bbox_x, _bbox_y = [],[]
for (min_dec,max_dec),(min_ha,max_ha) in HORIZON_BOX.items():
    _bbox_x.append(min_ha); _bbox_y.append(min_dec)
    _bbox_x.append(min_ha); _bbox_y.append(max_dec)
    _bbox_x.append(max_ha); _bbox_y.append(min_dec)
    _bbox_x.append(max_ha); _bbox_y.append(max_dec)
_bbox_x = np.array(_bbox_x)
_bbox_y = np.array(_bbox_y)

neg_x = _bbox_x[_bbox_x<0]
neg_x_y = _bbox_y[_bbox_x<0]
pos_x = _bbox_x[_bbox_x>=0]
pos_x_y = _bbox_y[_bbox_x>=0]
bbox_x = np.concatenate([neg_x,pos_x[::-1],[neg_x[0]]])
bbox_y = np.concatenate([neg_x_y,pos_x_y[::-1],[neg_x_y[0]]])


class ObsConstraint:
    def __init__(self, flip_box=False):
        if flip_box:
            self.horizon_box = FLIPPED_BOX
        else:
            self.horizon_box = HORIZON_BOX
        self.is_box_flipped = flip_box
        self.locationInfo = observatory_location
        # self._dec_vertices = list(set([item for key in self.horizon_box.keys() for item in
        #                  key]))  # this is just a list of integers, each being one member of one of the dec tuples that are the keys to the horizonBox dictionary
        # self._dec_vertices.sort()
        # # self.horizon_box_vertices = self.get_horizon_box_vertices()
    
    def get_obs_lst(self,kind="mean"):
        return get_current_sidereal_time(self.locationInfo,kind=kind)

    def get_hour_angle_limits(self,dec):
        """
        Get the hour angle limits of the target's observability window based on its dec.
        @param dec: float, int, or astropy Angle
        @return: A tuple of Angle objects representing the upper and lower hour angle limits
        """
        dec = ensureFloat(dec)
        for decRange in self.horizon_box:
            if decRange[0] < dec <= decRange[1]:  # man this is miserable
                finalDecRange = self.horizon_box[decRange]
                return tuple([Angle(finalDecRange[0], unit=u.deg), Angle(finalDecRange[1], unit=u.deg)])
        return None        
    
    def static_observability_window(self, RA: Angle, Dec: Angle, target_dt=None,
                              current_sidereal_time=None):
        """!
        Generate the TMO observability window for a static target based on RA, dec, and location
        @param RA: right ascension
        @param Dec: declination
        @param locationInfo: astral LocationInfo object for the observatory site
        @param target_dt: find the next transit after this time. if None, uses currentTime
        @param current_sidereal_time: optional: the current sidereal time. calculating this ahead with observing_utils.get_current_sidereal_time and providing it to each function call vastly improves performance. will add sidereal days to this if necessary
        @return: [startTime, endTime]
        @rtype: list(datetime)
        """
        current_sidereal_time = current_sidereal_time if current_sidereal_time is not None else self.get_obs_lst()

        target_dt = target_dt or current_dt_utc()
        t = find_transit_time(ensureAngle(RA), self.locationInfo, current_sidereal_time=current_sidereal_time,
                            target_dt=target_dt)
        time_window = (angleToTimedelta(a) for a in self.get_hour_angle_limits(Dec))
        return [t + a for a in time_window]
        # HA = ST - RA -> ST = HA + RA

    def get_sunrise_sunset(self, dt=None, jd=False,verbose=False):
        """!
        get sunrise and sunset for TMO
        @return: sunriseUTC, sunsetUTC
        @rtype: datetime.datetime
        """
        dt = dt or current_dt_utc()
        return get_sunrise_sunset(self.locationInfo, dt=dt, jd=jd, verbose=False)
    
    def get_RA_window(self, target_dt, dec, ra=None, current_sidereal_time=None):
        # get the bounding RA coordinates of the TMO observability window for time target_dt for targets at declination dec. Optionally, input an RA to also get out that RA, adjusted for box-shifting

        current_sidereal_time = current_sidereal_time if current_sidereal_time is not None else self.get_obs_lst()
        adjusted_ra = ra.copy() if ra is not None else None
        hourAngleWindow = self.get_hour_angle_limits(dec)
        if not hourAngleWindow: return False
        raWindow = [dateToSidereal(target_dt, current_sidereal_time) - hourAngleWindow[1],
                    (dateToSidereal(target_dt, current_sidereal_time) - hourAngleWindow[0]) % Angle(360, unit=u.deg)]

        # we want something like (23h to 17h) to look like [(23h to 24h) or (0h to 17h)] so we move the whole window to start at 0 instead
        if raWindow[0] > raWindow[1]:
            diff = Angle(24, unit=u.hour) - raWindow[0]
            raWindow[1] += diff
            if adjusted_ra is not None:
                adjusted_ra = (adjusted_ra + diff) % Angle(360, unit=u.deg)
            raWindow[0] = Angle(0, unit=u.deg)
        return raWindow, adjusted_ra

    # def get_horizon_box_vertices(self):
    #     horizon_box_vertices = []
    #     for dec in self._dec_vertices:
    #         for offset in (0.5,-0.5):
    #             window = self.get_hour_angle_limits(dec+offset)
    #             if not window:
    #                 continue
    #             window = [a.deg for a in window]
    #             horizon_box_vertices.append((window[0],dec))
    #             horizon_box_vertices.append((window[1],dec))
    #     # put the vertices in clockwise order

    #     # find the centroid of the points
    #     centroid = get_centroid(horizon_box_vertices)
    #     # sort the points based on their angles with respect to the centroid
    #     ordered_vertices = sorted(horizon_box_vertices, key=lambda point: get_angle(point, centroid, centroid))
    #     # append the first vertex at the end to close the polygon
    #     ordered_vertices.append(ordered_vertices[0])
    #     # fix annoying shape malformation
    #     # if self.flipped_box:
    #     #     ordered_vertices[30], ordered_vertices[31] = ordered_vertices[31], ordered_vertices[30]
    #     # else:
    #     #     ordered_vertices[42], ordered_vertices[43] = ordered_vertices[43], ordered_vertices[42]

    #     return ordered_vertices

    def observation_viable(self, dt: datetime, ra: Angle, dec: Angle, current_sidereal_time=None, ignore_night=False, debug=False, dbg_not_obs = False):
        """
        Can a target with RA ra and Dec dec be observed at time dt? Checks hour angle limits based on TMO bounding box.
        @return: bool
        """
        logger = logging.getLogger(__name__)
        current_sidereal_time = current_sidereal_time if current_sidereal_time is not None else self.get_obs_lst()
        HA_window = self.get_hour_angle_limits(dec)
        if not HA_window:
            return False
        HA = get_hour_angle(ra, dt, current_sidereal_time)
        night_time = self.is_at_night(dt)
        # NOTE THE ORDER:
        # if self.flipped_box:
        #     return HA.is_within_bounds(HA_window[1], HA_window[0]) and night_time
        obs_viable = HA.is_within_bounds(HA_window[0], HA_window[1]) and (night_time or ignore_night)
        if dbg_not_obs and not obs_viable:
            logger.info(f"[Observability Calculation] RA: {ra}, Dec: {dec}, HA: {HA}, HA Window: {HA_window}, Night: {night_time}, Obs time: {dt}, Obs LST: {dateToSidereal(dt,current_sidereal_time)}, Viable: {obs_viable}")
        elif debug:
            logger.info(f"[Observability Calculation] RA: {ra}, Dec: {dec}, HA: {HA}, HA Window: {HA_window}, Night: {night_time}, Viable: {obs_viable}")
        return obs_viable
    
    def is_at_night(self,dt:datetime):
        """ Is it night at TMO at time dt?"""
        sunrise, sunset = self.get_sunrise_sunset(dt)
        return sunset < dt < sunrise

    def observability_mask(self,table:QTable,current_sidereal_time=None,ra_column="ra",dec_column="dec",dt_or_column="dt", ignore_night=False):
        """ Take a table of candidates and return a mask of which ones are observable at the given time (or times if dt_or_column is the name of a column)"""
        current_sidereal_time = current_sidereal_time if current_sidereal_time is not None else self.get_obs_lst()
        mask = np.zeros(len(table),dtype=bool)
        for i,row in enumerate(table):
            if isinstance(dt_or_column,str):
                dt = row[dt_or_column]
            else:
                dt = dt_or_column
            mask[i] = self.observation_viable(dt,row[ra_column],row[dec_column],current_sidereal_time=current_sidereal_time,ignore_night=ignore_night)
        return mask
    
    def plot_bbox(self,ax,**kwargs):
        """ Plot the TMO bounding box on the given axes"""
        kwargs["color"] = kwargs.get("color","green")
        kwargs["linestyle"] = kwargs.get("linestyle","dashed")
        return ax.plot(bbox_x,bbox_y,**kwargs)

    def plot_onsky(self, dt=None,candidates=None,current_sidereal_time=None, ax=None, crop_to_bbox=False,observable_only=False):
        """ Take a list of candidates, create a plot of them onsky (plus sunrise, sunset, and bbox) and return the figures, axes and artists (to allow animation)"""
        if dt is None:
            dt = current_dt_utc()
        sunrise, sunset = self.get_sunrise_sunset(dt)
        current_sidereal_time = current_sidereal_time if current_sidereal_time is not None else get_current_sidereal_time(self.locationInfo)
        sidereal = dateToSidereal(dt, current_sidereal_time)
        names = [c.CandidateName for c in candidates]
        ras = [c.RA for c in candidates]
        decs = [c.Dec for c in candidates]
        table = QTable([names,ras,decs],names=["name","RA","Dec"])
        
        table["HA"] = [get_hour_angle(ra,dt,current_sidereal_time).deg for ra in table["RA"]]
        if observable_only:
        # make column indicating which targets are observable  - this line used to look for obs viable at dt-timedelta(day=1), not sure why:
            table["Observable"] = [self.observation_viable(dt,Angle(row["RA"],unit='deg'),Angle(row["Dec"],unit='deg'), current_sidereal_time=current_sidereal_time, ignore_night=True) for row in table]
            data = table[table["Observable"]]
        else:
            data = table

        figsize = (20,5)
        if ax is None:
            _, ax = plt.subplots(figsize=figsize)

        if not crop_to_bbox:
            xlimits = (-180,180)
            ylimits = (-90,90)
        else:
            # graph min x, min y need to become more negative if already negative else less positive
            x_min_coeff = 1.1 if min(bbox_x) < 0 else 0.9
            xlimits = (x_min_coeff*min(bbox_x),1.1*max(bbox_x))
            y_min_coeff = 1.1 if min(bbox_y) < 0 else 0.9
            ylimits = (y_min_coeff*min(bbox_y),1.1*max(bbox_y))


        artists_ls = []
        colors = plt.cm.tab20(np.linspace(0, 1, len(data)))
        ax.cla()
        ax.set_xlabel('HA (deg)')
        ax.set_ylabel('Dec (deg)')
        plt.axis('scaled')
        ax.set_xlim(*xlimits)
        ax.set_ylim(*ylimits)
        plt.title(f"Observability at {dt.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        sunr, suns = dateToSidereal(sunrise,current_sidereal_time), dateToSidereal(sunset, current_sidereal_time)
        sunr, suns = sunr-sidereal, suns-sidereal
        sunr, suns = wrap_around(sunr.deg), wrap_around(suns.deg)
        sunrise_line = ax.axvline(x=sunr, linestyle='--', color='red')
        sunset_line = ax.axvline(x=suns, linestyle='--', color='blue')

        if suns < sunr:
            fill = ax.axvspan(suns, sunr, alpha=0.2, color='gray')
        else:
            fill1 = ax.axvspan(xlimits[0],sunr,alpha=0.2,color="gray")
            fill2 = ax.axvspan(suns,xlimits[1],alpha=0.2,color="gray")

        # draw the bbox
        bbox = self.plot_bbox(ax)

        artists = [bbox,sunrise_line,sunset_line]
        
        # to label the vertices of the box for debugging:
        # for i, p in enumerate(zip(x,y)):
        #     px,py = p
        #     artists.append(ax.text(px,py,s=str(i)))

        for i, row in enumerate(data):
            artists.append(ax.scatter(row["HA"], row["Dec"], c=[colors[i]], label=row["name"],s=10))
        artists_ls.append(artists)
        return ax, artists_ls, data
    
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