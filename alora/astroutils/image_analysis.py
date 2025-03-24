# average_fwhm
# bkg, std
# source_catalog

import sys
from os.path import join, splitext, basename, dirname
import argparse
import glob
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from photutils.segmentation import deblend_sources
from astropy.convolution import Gaussian2DKernel, convolve
from astropy.stats import gaussian_fwhm_to_sigma
from photutils.segmentation import detect_sources
from photutils.segmentation import SourceCatalog
from astropy.stats import sigma_clipped_stats
from typing import List, Union
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm

import warnings
warnings.filterwarnings('ignore', module="astropy.table.groups")

PRECISION = {
    16:np.float16,
    32:np.float32,
    64:np.float64
}

def read_fits(path,frame=0,wcs=False):
    with fits.open(path) as hdul:
        data = hdul[frame].data + 0
        header = hdul[frame].header
        if wcs:
            wcs = WCS(header)
            return data, header, wcs
    return data, header
               

def segmentation(data:np.ndarray, threshold:float, npixels:int, fwhm_pix=None):
    d = data
    if fwhm_pix is not None:
        sigma = fwhm_pix * gaussian_fwhm_to_sigma
        kernel = Gaussian2DKernel(sigma)
        d = convolve(data, kernel, normalize_kernel=True)
    segm = detect_sources(d, threshold, npixels=npixels)
    return data, segm


def deblending(convolved_data, segm, npixels, nlevels, contrast):
	segm_deblend = deblend_sources(convolved_data, segm, npixels, nlevels=nlevels, contrast=contrast,progress_bar=False)
	return segm_deblend

def calc_bkg(data:np.ndarray, sigma=3):
    _, median, std = sigma_clipped_stats(data, sigma=sigma)
    return median, std

def bkg_subtracted(data,sigma=3):
    median, _ = calc_bkg(data, sigma=sigma)
    return data - median

# given source data, create a source catalog
def source_catalog(data:np.ndarray, source_sigma, ncont, precision=np.float32, fwhm_pix=None,extra_cols:list[str]|None=None):
    data = data.astype(precision)
    median, std = calc_bkg(data, sigma=3)
    threshold = source_sigma * std
    data -= median.astype(precision)

    npixels = ncont   # number of connected pixels needed, each above threshold, for an area to qualify as a source
    convolved_data, segm = segmentation(data, threshold, npixels, fwhm_pix)
    if convolved_data is None or segm is None:
        return None
    segm_deblend = deblending(convolved_data, segm, npixels, nlevels=16, contrast=0.001)

    cat = SourceCatalog(data, segm_deblend, convolved_data=convolved_data)
    if extra_cols is None:
         extra_cols = []
    table = cat.to_table(columns=cat.default_columns+extra_cols+["fwhm"])

    # table[np.where(table["kron_flux"]<1)] = 0    # don't remember why i did this, commenting for now (sjs 9/25/2024)

    table.sort(['kron_flux'], reverse = True)
    return table


def calc_mean_fwhm(data:np.ndarray, source_sigma=5, ncont=16, precision=np.float32, return_catalog=False):
    catalog = source_catalog(data, source_sigma, ncont, precision=precision)
    if not len(catalog):
         raise ValueError("No sources detected in image!")
    mean_cat = catalog.groups.aggregate(np.mean)
    mean_fwhm = float(mean_cat["fwhm"][0].to_value("pix"))

    # catalog = source_catalog(data, source_sigma, ncont, precision=precision, fwhm_pix=mean_fwhm)
    # mean_cat = catalog.groups.aggregate(np.mean)
    # mean_fwhm = float(mean_cat["fwhm"][0].to_value("pix"))
    if return_catalog:
        return mean_fwhm, catalog
    return mean_fwhm

