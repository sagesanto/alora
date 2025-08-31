import math
import shutil

import matplotlib.markers
import numpy as np
import pandas as pd
from pandas_profiling import ProfileReport
from alora.maestro.scheduleLib.candidateDatabase import Candidate, CandidateDatabase
from alora.maestro.scheduleLib import genUtils
import os
import matplotlib.pyplot as plt
from collections import namedtuple


def mkdirIfNotExists(path, overwrite=False):
    if not os.path.exists(path):
        os.mkdir(path)
    elif overwrite:
        try:
            shutil.rmtree(path, ignore_errors=True)
            os.mkdir(path)
        except:
            pass


RED = "#FF0000"
GREEN = "#00FF00"

candidateDb = CandidateDatabase("files/candidate database.db", "Target Stats Query")
candidateDb.db_cursor.execute("SELECT * FROM Candidates WHERE CandidateType is \"MPC NEO\"")

candidates = candidateDb.queryToCandidates(candidateDb.db_cursor.fetchall())

df = Candidate.candidatesToDf(candidates)

doReport = False
overwrite = True
savepath = "files/TMO_target_queries"

reportSavePath = os.path.join(savepath, "reports")
csvSavePath = os.path.join(savepath, "csvs")
plotSavePath = os.path.join(savepath, "plots")

if not os.path.exists(savepath):
    os.mkdir(savepath)
    os.mkdir(reportSavePath)
    os.mkdir(csvSavePath)
    os.mkdir(plotSavePath)
elif overwrite:
    try:
        shutil.rmtree(reportSavePath, ignore_errors=True)
        os.mkdir(reportSavePath)
        shutil.rmtree(csvSavePath, ignore_errors=True)
        os.mkdir(csvSavePath)
        shutil.rmtree(plotSavePath, ignore_errors=True)
        os.mkdir(plotSavePath)
    except:
        pass

allGhosts = list(pd.read_csv("files/tmo_ghosts.csv")["Temp_Desig"])
recentGhosts = list(pd.read_csv("files/tmo_ghosts__since_september.csv")["Temp_Desig"])
tmo_success = list(pd.read_csv("files/tmo_successes.csv")["Temp_Desig"])

allGhosts = df[df["CandidateName"].isin(allGhosts)]
allGhosts.to_csv(os.path.join(csvSavePath, "allGhosts.csv"))

recentGhosts = df[df["CandidateName"].isin(recentGhosts)]
recentGhosts.to_csv(os.path.join(csvSavePath, "recentGhosts.csv"))

tmo_success = df[df["CandidateName"].isin(tmo_success)]
tmo_success.to_csv(os.path.join(csvSavePath, "tmoSuccess.csv"))

if doReport:
    allGhostsReport = ProfileReport(allGhosts)
    allGhostsReport.to_file(os.path.join(reportSavePath, "allGhostsReport.html"))

    tmo_successReport = ProfileReport(tmo_success)
    tmo_successReport.to_file(os.path.join(reportSavePath, "tmo_successReport.html"))

    recentGhostsReport = ProfileReport(recentGhosts)
    recentGhostsReport.to_file(os.path.join(reportSavePath, "recentGhostsReport.html"))

    comparison_report = tmo_successReport.compare(recentGhostsReport)
    comparison_report.to_file(os.path.join(reportSavePath, "success_ghost_comparison.html"))

GraphDf = namedtuple("GraphDf", ['df', 'color', 'alpha', 'size', 'marker'])
tmo_success_graphdf = GraphDf(tmo_success, 'green', 1, 10, '+')
recentGhosts_graphdf = GraphDf(recentGhosts, 'red', 1, 10, 'x')
all_graphdf = GraphDf(df, 'blue', 0.25, 2, 'o')

dfPairs = [(all_graphdf, tmo_success_graphdf, "Successes vs All"),
           (recentGhosts_graphdf, tmo_success_graphdf, "Recent Ghosts vs Successes"),
           (all_graphdf, recentGhosts_graphdf, "Recent Ghosts vs All")]

# scatter plots
# (col1name, col2name, plotTitle)
scatterColumnPairs = [("RA", "Dec", "RA vs Dec"), ("RMSE_RA", "RMSE_Dec", "RA vs Dec RMSE"),
                      ("dRA", "dDec", "dRA vs dDec")]
for dfPair in dfPairs:
    savedir = os.path.join(plotSavePath, dfPair[2].replace(" ", "_"))
    mkdirIfNotExists(savedir, overwrite=True)
    for columnPair in scatterColumnPairs:
        print(columnPair)
        plt.xlim(100)
        plt.ylim(100)
        fig, ax = plt.subplots()
        print(dfPair)
        ax.scatter([v for v in dfPair[0].df[columnPair[0]]],
                   [v for v in dfPair[0].df[columnPair[1]]], c=dfPair[0].color, alpha=dfPair[0].alpha,
                   s=dfPair[0].size, marker=dfPair[0].marker)
        ax.scatter([v for v in dfPair[1].df[columnPair[0]]],
                   [v for v in dfPair[1].df[columnPair[1]]], c=dfPair[1].color, alpha=dfPair[1].alpha,
                   s=dfPair[1].size, marker=dfPair[1].marker)
        plt.suptitle(dfPair[2])
        plt.title(columnPair[2])
        plt.xlabel(columnPair[0])
        plt.ylabel(columnPair[1])
        plt.savefig(os.path.join(savedir, columnPair[2].replace(" ", "_") + ".png"))
        plt.show()
        plt.clf()

histColumnPairs = [("Magnitude", "Magnitude"), ("Approach Color", "Approach Color")]
for dfPair in dfPairs:
    for columnPair in histColumnPairs:
        # print(dfPair[2])
        # maX = max(dfPair[0].df[columnPair[0]])
        # print("max:",maX)
        # print(dfPair[0].df[dfPair[0].df[columnPair[0]]==maX])
        # print("bin1:", math.floor(max([v for v in dfPair[0].df[columnPair[0]] if v != 99.9])+1 - min(dfPair[0].df[columnPair[0]])))
        # print("bin2:", math.floor(max(dfPair[1].df[columnPair[0]])+1 - min(dfPair[1].df[columnPair[0]])))
        binNum = max(math.floor(max(dfPair[0].df[columnPair[0]]) + 1 - min(dfPair[0].df[columnPair[0]])),
                     math.floor(max(dfPair[1].df[columnPair[0]]) + 1 - min(dfPair[1].df[columnPair[0]])))
        fig, ax = plt.subplots()
        ax.hist([float(v) for v in dfPair[0].df[columnPair[0]] if v], bins=binNum,
                color=dfPair[0].color, alpha=dfPair[0].alpha)
        ax.hist([float(v) for v in dfPair[1].df[columnPair[0]] if v], bins=binNum,
                color=dfPair[1].color, alpha=dfPair[1].alpha)
        # ax.hist(dfPair[1].df[columnPair[0]].astype(np.float16), dfPair[1].df[columnPair[1]].astype(np.float16),
        #            color=dfPair[1].color, alpha=dfPair[1].alpha, s=dfPair[1].size, marker=dfPair[1].marker)
        plt.suptitle(dfPair[2])
        plt.title(columnPair[1])
        plt.xlabel(columnPair[0])
        plt.ylabel("Num Targets")
        plt.savefig(os.path.join(savedir, columnPair[1].replace(" ", "_") + ".png"))
        plt.show()
        plt.clf()

df.to_csv(os.path.join(csvSavePath, "allCandidates.csv"))
