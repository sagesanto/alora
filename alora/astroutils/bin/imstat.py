#! python

import sys
from os.path import join, splitext, basename, dirname
import argparse
import glob
import numpy as np
from alora.astroutils.image_analysis import calc_mean_fwhm, segmentation, deblending, source_catalog
from astropy.io import fits
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

def calculate_image_statistics(images:List[str], subregion:Union[List[int],None]=None, precision=np.float32, save_catalog:bool=False, do_fwhm:bool=True, source_sigma=5, ncont=16, visualize:bool=False):
    # Initialize lists to store statistics for each image
    subregion = subregion or []
    statistics = []
    labels = ["Pixels","Mean","Median","StdDev","Min", "Max"]
    if do_fwhm:
        labels.extend(("FWHM","NumSources"))
    
    precision = PRECISION[precision]

    # Loop through the list of images
    for image_file in images:
        try:
            # Open the FITS image
            hdul = fits.open(image_file)
            # if we are going to calculate the fwhm, get the data at the float precision specified by the user (default 32)
            if do_fwhm:
                data = hdul[0].data.astype(precision)
            else:
                # otherwise, don't do that (saves memory)
                data = hdul[0].data

            if len(subregion)==4:
                x1=subregion[0]-1
                x2=subregion[1]
                y1=subregion[2]-1
                y2=subregion[3]

            if len(subregion)==0:
                x1=0
                x2=data.shape[0]
                y1=0
                y2=data.shape[1]

            # Calculate statistics

            frame = data[x1:x2,y1:y2]

            mean = np.mean(frame)
            median = np.median(frame)
            std_dev = np.std(frame)
            min_value = np.min(frame)
            max_value = np.max(frame)
            total_pixels = frame.size

            # Append the statistics to the list

            d_list = [image_file, total_pixels, mean, median, std_dev, min_value, max_value] 

            if do_fwhm:
                f, catalog = calc_mean_fwhm(frame, source_sigma, ncont, precision,return_catalog=True)
                num = len(catalog)
                d_list.append(f)
                d_list.append(num)
                if visualize:
                    plt.imshow(frame,cmap="gray",origin="lower",vmin=median-std_dev,vmax=max_value)
                    plt.scatter(catalog["xcentroid"],catalog["ycentroid"],alpha=0.25)
                    plt.show()
                if save_catalog:
                    fname = splitext(basename(image_file))[0] + ".cat.csv"
                    # currently, we'll save these into the current directory. maybe it would be better to save into the fits file's dir
                    catalog.write(fname,overwrite=True)

            statistics.append(d_list)

            # Close the FITS file
            hdul.close()

        except Exception as e:
            print(f"Error processing {image_file}: {str(e)}")

    return statistics, labels

def main():
    # Create a command-line argument parser
    parser = argparse.ArgumentParser(description="Calculate statistics for a list of FITS images.")
    
    # Define a positional argument to accept a list of FITS image files or wildcards
    parser.add_argument("filenames", nargs="+", help="List_of_FITS_image_files_or_wildcards")

#    # Define an optional argument to specify the list of header keywords to print (pic - 09.23.24)
    parser.add_argument("-s", "--subregion",  nargs=4, type=int, help="2-d subregion on which to perform stats: syntax: xmin xmax ymin ymax")

    # Define optional argument to toggle source extraction and FWHM calculation (sjs - 09/25/24)
    parser.add_argument('-d','--deluxe', dest='deluxe', action='store_true', help="Calculate image stats, run source extraction, and do fwhm calculation on the frame. Default.")
    parser.add_argument('-p','--plain', dest='deluxe', action='store_false', help="Calculate image stats only, no source extraction")
    parser.set_defaults(deluxe=True)

    # Define optional argument to change float precision (when in deluxe mode) (sjs - 09/25/24)
    parser.add_argument("--precision", default=32, type=int, help=f"Desired float precision, one of {list(PRECISION.keys())}. Default 32. Ignored if --deluxe is False.")

    # Define optional argument to toggle saving created source catalogs (when in deluxe mode) (sjs - 09/25/24)
    parser.add_argument("-c", "--save-catalog", default=False, action="store_true", help="Whether, if when running in deluxe mode, to store the created source catalog for each image as a csv. Default False.")

    parser.add_argument("--source-sigma", default=5, type=float, help="how many standard deviations above the noise a source must be to be detected in deluxe mode. Default 5.")

    parser.add_argument("--ncont", default=16, type=int, help="number of sufficiently-bright connected pixels a source must have to be detected in deluxe mode. Default 16.")

    parser.add_argument("-v", "--visualize", default=False, action="store_true", help="Whether, if when running in deluxe mode, to plot the source catalog on the image for each frame")


    # Parse the command-line arguments
    args = parser.parse_args()
    
    # Get the list of filenames or wildcard patterns provided as arguments
    filenames = args.filenames

    # Get the subarray string
    subregion = args.subregion or []

    # Use glob to expand wildcards and find matching files
    matching_files = []
    for pattern in filenames:
        matching_files.extend(glob.glob(pattern))
    if not matching_files:
        print("No matching files found.")
        sys.exit(1)
    print(f"Running on {len(matching_files)} frame{'s' if len(matching_files)>1 else ''}: {', '.join(matching_files)}")

    deluxe = args.deluxe

    precision = args.precision
    try:
        precsision = PRECISION[precision]
    except KeyError:
        print(f"ERROR: --precision must be one of {list(PRECISION.keys())}, not '{precision}'")
        sys.exit(1)

    save_catalog = args.save_catalog

    source_sigma = args.source_sigma
    ncont = args.ncont
    visualize = args.visualize

    # Calculate statistics for the matching FITS images
    statistics, labels = calculate_image_statistics(matching_files, subregion, precision, save_catalog, do_fwhm=deluxe, source_sigma=source_sigma, ncont=ncont, visualize=visualize)

    # Print the statistics for each image
    for stats in statistics:
        strs = [f"{s:.2f}" if np.issubdtype(type(s), np.floating) else str(s) for s in stats]
        print("")
        print(f"{strs[0]}:")
        
        data_sep = max(len(s) for s in strs[1:-1])
        label_sep = max(len(s) for s in labels[:-1])
        sep = max(data_sep,label_sep)+1
        labels = [f"{l:<{sep}}" for l in labels]
        strs = [f"{s:<{sep}}" for s in strs]
        print(" ".join(labels))
        print(" ".join(strs[1:]))

if __name__ == "__main__":
    main()