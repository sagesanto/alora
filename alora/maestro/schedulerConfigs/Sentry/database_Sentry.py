import requests
import json, os, sys
from os.path import dirname, join, abspath, pardir
import urllib
from datetime import datetime, timedelta
from io import StringIO, BytesIO
import pytz
import asyncio

import numpy as np

import astropy.table
from astropy.table import vstack, QTable, Table
from astroquery.jplhorizons import Horizons

from alora.maestro.schedulerConfigs.Sentry.sentry_ephem_cache import SentryEphemCache
from alora.astroutils.observing_utils import dt_to_jd, jd_to_dt, find_transit_time, get_current_sidereal_time
from alora.astroutils.obs_constraints import ObsConstraint
from alora.config.utils import configure_logger, Config
from alora.config import logging_dir
from alora.maestro.scheduleLib.candidateDatabase import CandidateDatabase, Candidate

SENTRY_DIR = dirname(abspath(__file__))

s_config = Config(join(SENTRY_DIR,"config.toml"))
logger = configure_logger("Sentry",join(logging_dir,'sentry.log'))
obs = ObsConstraint()

min_impact = s_config["min_impact_prob"]
print(min_impact)

eph_cache = SentryEphemCache(logger)

def get_sentry(params):
    client = requests.session()
    # TODO: read params for search filtering from config
    query = s_config["sentry_endpoint"]
    if params:
        query += "?" + "&".join([f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items()])
    response = client.get(query)
    return json.loads(response.content)

def fetch_sentry_list():
    p = {"all":1,"ip-min":min_impact}
    p_prime = s_config.get("sentry_search_params",default={})
    if p_prime:
        p.update(p_prime)
    data = get_sentry(p)
    print(data)
    if data["signature"]["version"] != "2.0":
        print(f"WARNING: API version mismatch. Sentry module designed for Sentry API v2.0 but got v{data['signature']['version']}")
    objects = data["data"]
    return objects

def update_database(db_path):
    # get the list of sentry objects
    # for each object, look and see if it's in the candidate database. if it's not, add it.
        # maintain the candidate list
    # for each object in the list of candidates, update the candidate's information
    # for each object in the list of candidates, update the candidate's observability
    # update the db with the new information

    objects = fetch_sentry_list()
    desigs = [o["des"] for o in objects]
    observability = calc_observability(desigs)
    db = CandidateDatabase(db_path,"Sentry")

    candidates = {}
    existing = db.getCandidatesByType("Sentry")
    existing = {} if existing is None else {c.CandidateName: c for c in existing if c is not None}
    current_lst = get_current_sidereal_time(obs.locationInfo)
    for o in objects:
        desig = o["des"]
        if desig in candidates.keys():
            # this can happen if the same object is returned multiple times because of multiple impacts. 
            # idk what to do about properly accumulating impact probabilities
            continue
        # load an ephem to get the current position
        e = asyncio.run(eph_cache.get_data([desig],datetime.now(pytz.utc)))[desig] 
        if e is None:
            logger.warning(f"Couldn't get ephems for {desig}. Skipping.")
            continue
        ra, dec = e[0]["RA"], e[0]["DEC"]
        obs_window = observability[desig]
        if obs_window is None:
            start, end = None, None
        else:
            start, end = obs_window
        if desig in existing.keys():
            c = existing[desig]
        else:  # need to create a new Candidate object
            c = Candidate(desig, "Sentry",RA=ra,Dec=dec, Priority = s_config["priority"])
            c.ID = db.insertCandidate(c)
        c.StartObservability = start
        mag = min(e["V"])
        c.Magnitude=mag.to_value()
        print("Magnitude: ",mag.to_value())
        if mag.to_value() > s_config["mag_limit"]:
            c.RejectedReason="Magnitude"
        c.Priority = s_config["priority"]
        c.RA, c.Dec = ra, dec
        c.TransitTime = find_transit_time(ra,obs.locationInfo,datetime.now(pytz.utc),current_sidereal_time=current_lst)
        c.EndObservability = end
        c.CVal1 = o["ps"]
        c.CVal2 = o["ip"]
        c.CVal3 = o["date"]
        candidates[desig] = c
        db.editCandidateByID(c.ID,c.asDict())
        # check if it's in the database
        # if it's not, add it

    # ephems = asyncio.run(eph_cache.get_data(desigs,datetime.now(pytz.utc)))
    # print(ephems)



def calc_observability(desigs):
    windows = {}
    need_to_fetch = []
    good_desigs = []
    ephems = asyncio.run(eph_cache.get_data(desigs,datetime.now(pytz.utc)))
    # data will be a dictionary of {desig: Astropy table}
    # tables will have columns "datetime_jd","RA","DEC","RA_app","DEC_app","RA_rate","DEC_rate","V","hour_angle"
    FETCH_UNTIL = datetime.now(pytz.UTC) + timedelta(hours=s_config["ephem_lookahead_hours"]+1)
    for d in desigs:
        if d not in ephems.keys() or ephems[d] is None:
            logger.warning(f"Couldn't get ephems and so can't calculate observability window for {d}. Skipping.")
            windows[d] = None
        else:
            good_desigs.append(d)
    for d,e in ephems.items():
        if jd_to_dt(e[-1]["datetime_jd"]) < FETCH_UNTIL:
            need_to_fetch.append(d)
    while len(need_to_fetch):
        logger.info(f"Getting more ephems for {len(need_to_fetch)} Sentry targets.")
        earliest_end = min([jd_to_dt(ephems[desig][-1]["datetime_jd"])+timedelta(minutes=1) for desig in need_to_fetch])
        more_eph = asyncio.run(eph_cache.get_data(need_to_fetch, earliest_end))
        for desig in need_to_fetch.copy():
            if desig not in more_eph.keys() or more_eph[desig] is None:
                logger.warning(f"Got some ephems but couldn't get more for {desig}")
                need_to_fetch.remove(desig)
                continue
            try:

                if astropy.table.column.MaskedColumn in [type(ephems[desig][c]) for c in ephems[desig].columns]:
                    print("Converting masked ephem table to QTable")
                    ephems[desig] = QTable(ephems[desig])
                    print(ephems[desig]["RA"])
                if astropy.table.column.MaskedColumn in [type(more_eph[desig][c]) for c in more_eph[desig].columns]:
                    print("Converting masked extra ephem table to QTable")
                    more_eph[desig] = QTable(more_eph[desig])
                    print(more_eph[desig]["RA"])
                #     print(f"Filling masked values for {desig} ephemeris")
                #     ephems[desig] = ephems[desig].filled()
                ephems[desig] = vstack([ephems[desig],more_eph[desig]])
            except Exception as e:
                print(f"Error stacking ephems for {desig}")
                print({c:type(ephems[desig][c]) for c in ephems[desig].columns})
                print({c:type(more_eph[desig][c]) for c in more_eph[desig].columns})
                raise e
            ephems[desig].sort("datetime_jd")
            if jd_to_dt(ephems[desig][-1]["datetime_jd"]) >= FETCH_UNTIL:
                need_to_fetch.remove(desig)
    logger.info(f"Done getting ephems.")
    
    # now, determine the observability windows
    for d in good_desigs:
        eph = ephems[d]
        avg_dec = sum([e["DEC"] for e in eph])/len(eph)
        lims = obs.get_hour_angle_limits(avg_dec)
        if lims is None:
            windows[d] = None
            continue
        min_ha, max_ha = lims
        print(eph["hour_angle"])
        print(min_ha)
        obs_mask = (eph["hour_angle"] > min_ha) & (eph["hour_angle"] < max_ha)
        observable = np.where(obs_mask)[0]
        if not len(observable):
            windows[d] = None
            continue
        start_index = observable[0]
        unobs = [i for i in np.where(~obs_mask)[0] if i > start_index]
        if not unobs:
            end_index = len(eph)-1
        else:
            end_index = unobs[0]
        obs_start = eph[start_index]["datetime_jd"]
        obs_end = eph[end_index]["datetime_jd"]
        windows[d] = (jd_to_dt(obs_start.to_value()),jd_to_dt(obs_end.to_value()))
    return windows

if __name__ == "__main__":
    update_database("")