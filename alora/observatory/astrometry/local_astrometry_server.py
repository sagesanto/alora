from flask import Flask, request, jsonify
import subprocess
import os
from alora.astroutils import calc_mean_fwhm, source_catalog
from astropy.io import fits
from astropy.table import Table
from astropy.coordinates import SkyCoord, Angle
import astropy.units as u
import numpy as np

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

    args = ['solve-field', newpath] + flags
    for key in data:
        if key != 'filepath':
            args.append(f'--{key}')
            args.append(str(data[key]))
        print(f"{key}: {data[key]}")

    try:
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode != 0:
            return jsonify({'error': result.stderr}), 500

        return jsonify({'message': 'Astrometry.net processing complete', 'output': result.stdout}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/solve', methods=['POST'])
def solve():
    return _solve(request.get_json())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5555)