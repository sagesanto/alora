# Sage Santomenna 2023
# Basic string->(Angle)->string coordinate parser supporting decimal, colon-sep, and hmsdms forms

from astropy import units as u  # manage coords
from astropy.coordinates import SkyCoord  # manage coords


def readCoords(coordsLine):
    coords = coordsLine.replace('\n', "")
    try:
        coords = SkyCoord(coords, unit=(u.hourangle, u.deg))
    except:
        print(coords.split(" ")[0])
        print(coords.split(" ")[1])

        coords = SkyCoord(coords.split(" ")[0], coords.split(" ")[1], frame='icrs', unit='deg')
    return coords


def formatOutput(coords):
    decimal = coords.to_string("decimal").split(" ")
    sexagesimal = coords.to_string("hmsdms").split(" ")
    return ((decimal[0], decimal[1]), (sexagesimal[0], sexagesimal[1]))


def convertCoords(coords):
    astroCoords = readCoords(coords)
    return formatOutput(astroCoords)
