import os

import genUtils
from datetime import datetime, timedelta
from candidateDatabase import Candidate, CandidateDatabase
import numpy as np
from matplotlib import pyplot as plt


BLACK = [0, 0, 0]
RED = [255, 0, 0]
GREEN = [0, 255, 0]
BLUE = [0, 0, 255]
ORANGE = [255, 191, 0]
PURPLE = [221, 160, 221]

def visualizeObservability(candidates: list, beginDt, endDt, savepath, title, schedule=None):
    """!
    Visualize the observability windows of candidates as a stacked timeline.

    @param candidates: list of Candidate objects
    @param beginDt: time of beginning of observability window, datetime
    @param endDt: time of end of observability windows, datetime
    @param schedule: WIP: astropy Table output by a scheduler. if passed, will be overlaid over the graphics. (not functional)
    @type schedule: Table

    """
    # print(beginDt, endDt)
    # Filter candidates with observability windows
    observabilityCandidates = [c for c in candidates if
                               c.hasField("StartObservability") and c.hasField("EndObservability")]

    # Sort candidates by their start times (earliest to latest)
    observabilityCandidates.sort(key=lambda c: genUtils.stringToTime(c.StartObservability))

    # Calculate start and end timestamps
    xMin, xMax = (beginDt + timedelta(hours=7)).timestamp(), (endDt + timedelta(hours=7)).timestamp()
    windowDuration = xMax - xMin

    # Get the unique colors and calculate the number of bars per color
    numCandidates = len(observabilityCandidates)
    numColors = len(plt.cm.tab20.colors)

    # Generate a list of colors using a loop
    colors = []
    for i in range(numCandidates):
        colorIndex = i % numColors
        color = plt.cm.tab20(colorIndex)
        colors.append(color)

    # Set up the plot
    fig, ax = plt.subplots(figsize=(10, 7))
    colorDict = {"GREEN": GREEN, "ORANGE": ORANGE, "RED": RED, "BLACK": BLACK}

    # if schedule is not None:
    #     df = schedule.to_pandas()
    #     print(df)

    # Iterate over observability candidates and plot their windows
    for i, candidate in enumerate(observabilityCandidates):
        # TODO: take the time to actually figure out why the UTC stuff doesn't work instead of just applying this hardcoded offset:
        startTime = genUtils.stringToTime(candidate.StartObservability)  # UTC conversion. this sucks
        endTime = genUtils.stringToTime(candidate.EndObservability)

        # Convert start time and end time to Unix timestamps
        startUnix = startTime.timestamp()
        endUnix = endTime.timestamp()

        # Calculate the duration of the observability window
        duration = endUnix - startUnix

        # Plot a rectangle representing the observability window
        ax.barh(i, duration, left=startUnix, height=0.6, color=np.array(colorDict[candidate.ApproachColor]) / 255)

        # Place the label at the center of the bar
        ax.text(max(startUnix + duration / 2, xMin + duration / 2), i, candidate.CandidateName, ha='center',
                va='center', bbox={'facecolor': 'white', 'alpha': 0.75, 'pad': 5})

    # Set the x-axis limits based on start and end timestamps
    ax.set_xlim(xMin, xMax + windowDuration / 10)

    # Format x-axis labels as human-readable datetime
    def formatFunc(value, tickNumber):
        dt = datetime.fromtimestamp(value)
        return dt.strftime("%H:%M\n%d-%b")

    ax.xaxis.set_major_formatter(plt.FuncFormatter(formatFunc))

    # Set the x-axis label
    ax.set_xlabel("Time (UTC)")

    # Set the y-axis label
    ax.set_ylabel("Candidates")

    # Adjust spacing
    plt.subplots_adjust(left=0.1, right=0.95, bottom=0.1, top=0.9)
    plt.suptitle("Candidates for Tonight")
    plt.title(
        beginDt.strftime("%b %d, %Y, %H:%M") + " to " + endDt.strftime(
            "%b %d, %Y, %H:%M"))

    # Show the plot
    plt.savefig(os.sep.join([savepath, title+".png"]))