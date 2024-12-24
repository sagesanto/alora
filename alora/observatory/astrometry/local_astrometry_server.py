import os
from os.path import join, dirname, abspath
import subprocess
from flask import Flask, request, jsonify
from alora.astroutils import calc_mean_fwhm, source_catalog
from astropy.io import fits
from astropy.table import Table
from astropy.coordinates import SkyCoord, Angle
import astropy.units as u
import numpy as np
import tomlkit

config_path = join(dirname(abspath(__file__)),"config.toml")
with open(config_path,"rb") as f:
    config = tomlkit.load(f)

logging_dir = abspath(join(dirname(abspath(__file__)),os.pardir,"logs"))

os.makedirs(logging_dir,exist_ok=True)
os.makedirs(config["SOLVE_DIR"],exist_ok=True)

app = Flask(__name__)

def make_source_cat(data:np.ndarray):
    mean_fwhm = calc_mean_fwhm(data)
    cat = source_catalog(data,source_sigma=3,ncont=5,fwhm_pix=mean_fwhm)
    return cat

def _solve(data):
    filepath = data.get('filepath').replace("D:\\", "/mnt/d/").replace("C:\\", "/mnt/c/")
    flags = data.get('flags', [])

    if not filepath or not os.path.isfile(filepath):
        return jsonify({'error': 'Invalid file path'}), 400
    
    with fits.open(filepath) as hdul:
        data = hdul[0].data
    
    cat = make_source_cat(data)
    newpath = filepath.replace(".fits", "_cat.fits")
    cat.write(newpath, format='fits', overwrite=True)

    data["width"] = data.shape[1]
    data["height"] = data.shape[0]
    data["xcolumn"] = "xcentroid"
    data["ycolumn"] = "ycentroid"

    wcspath = join(config["SOLVE_DIR"], filepath.replace(".fits", ".wcs"))
    data["wcs"] = wcspath

    args = ['solve-field', newpath] + flags
    for key in data:
        if key not in ['filepath',"flags"]:
            args.append(f'--{key}')
            args.append(str(data[key]))
        print(f"{key}: {data[key]}")

    try:
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode != 0:
            return jsonify({'error': result.stderr}), 500
        
        with fits.open(wcspath) as hdul:
            wcs_header = hdul[0].header

        with fits.open(filepath, mode='update') as hdul:
            header = hdul[0].header
            for key in ["CRVAL1", "CRVAL2", "CRPIX1", "CRPIX2", "CUNIT1", "CUNIT2", "CD1_1", "CD1_2", "CD2_1", "CD2_2"]:
                header[key] = wcs_header[key]

        return jsonify({'message': 'Astrometry.net processing complete', 'output': result.stdout}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/solve', methods=['POST'])
def solve():
    return _solve(request.get_json())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=config["PORT"])