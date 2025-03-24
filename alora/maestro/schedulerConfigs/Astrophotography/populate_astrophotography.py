import configparser
import sys, os, pandas as pd
from os.path import join, dirname, pardir, abspath

from astral import LocationInfo
from astroquery.simbad import Simbad

from alora.config import observatory_location

try:
    grandparentDir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir))
    sys.path.append(grandparentDir)
    from scheduleLib import genUtils
    from scheduleLib.candidateDatabase import Candidate

    sys.path.remove(grandparentDir)
    aConfig = genUtils.Config(join(dirname(__file__), "config.toml"))
    genConfig = genUtils.Config(os.path.join(grandparentDir, "files", "configs", "config.toml"))


except ImportError:
    from scheduleLib import genUtils
    from scheduleLib.candidateDatabase import Candidate

    aConfig = genUtils.Config(join(dirname(__file__), "config.toml"))
    genConfig = genUtils.Config(os.path.join("files", "configs", "config.toml"))

obs = observatory_location


def getData():
    simbad = Simbad()
    simbad.add_votable_fields('id(1,s)', 'otype(V)', 'flux(V,mag)', 'ra(d)', 'dec(d)', 'dim_majaxis')
    simbad.remove_votable_fields('coordinates', 'main_id')
    res = simbad.query_criteria(aConfig["simbad_query"])
    df = res.to_pandas().drop(labels="SCRIPT_NUMBER_ID", axis="columns")
    df.columns = ["CandidateName", "OType", "Magnitude", "RA", "Dec", "MajorAxis"]
    df["CandidateName"] = df.CandidateName.apply(
        lambda name: name.replace("  ", " ").replace("NAME ", "").replace("M ", "M"))
    df.to_csv("astroRes.csv", index=None)
    return df


def makeCandidatesFromDf(df: pd.DataFrame):
    candidates = []
    for i in range(len(df.index)):
        d = {}
        for j in ["Magnitude", "RA", "Dec"]:
            d[j] = float(df.iloc[i][j])
        d["CVal1"] = df.iloc[i]["MajorAxis"]
        d["CVal2"] = df.iloc[i]["OType"]
        d["Filter"] = "g, r, i"
        d['Processed'], d['Submitted'], d['dRA'], d['dDec'] = 0, 0, 0, 0
        d["TransitTime"] = genUtils.timeToString(
            genUtils.roundToTenMinutes(
                genUtils.find_transit_time(genUtils.ensureAngle(d["RA"]), obs)))
        candidates.append(Candidate(df.iloc[i]["CandidateName"], "Astrophotography", **d))
    return candidates


# -- to be run only to change the underlying targets, not to update them --
# program:
# get SIMBAD data
# clean and transform to df
# make candidates from df
# save as astroRes.csv for use by database_astrophotography.py

if __name__ == "__main__":
    df = getData()
    candidates = makeCandidatesFromDf(df)
    candidateDf = Candidate.candidatesToDf(candidates)
    candidateDf.to_csv("schedulerConfigs/Astrophotography/astroRes.csv", index=None)  # self-locating uncertainty
