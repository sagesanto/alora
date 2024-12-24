import os
from os.path import join, dirname, abspath
import subprocess
from flask import Flask, request, jsonify
from astropy.io import fits
from astropy.table import Table
from astropy.coordinates import SkyCoord, Angle
import astropy.units as u
import numpy as np
import tomlkit
import sqlite3

db_path = join(dirname(abspath(__file__)), "astrom.db")
conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute("CREATE TABLE IF NOT EXISTS astrometry (id INTEGER PRIMARY KEY AUTOINCREMENT, filepath TEXT, wcs TEXT, flags TEXT, status TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
conn.commit()
config_path = join(dirname(abspath(__file__)),"config.toml")
with open(config_path,"rb") as f:
    config = tomlkit.load(f)

logging_dir = abspath(join(dirname(abspath(__file__)),os.pardir,"logs"))

os.makedirs(logging_dir,exist_ok=True)
os.makedirs(config["SOLVE_DIR"],exist_ok=True)

app = Flask(__name__)

def create_record(filepath,wcspath,flags):
    cur.execute("INSERT INTO astrometry (filepath, wcs, flags, status) VALUES (?,?,?,?)",(filepath,wcspath,flags,"processing"))
    conn.commit()
    cur.execute("SELECT last_insert_rowid()")
    return cur.fetchone()[0]

def mark_solved(record_id):
    cur.execute("UPDATE astrometry SET status = 'solved' WHERE id = ?",(record_id,))
    conn.commit()

def mark_failed(record_id):
    cur.execute("UPDATE astrometry SET status = 'failed' WHERE id = ?",(record_id,))
    conn.commit()

def _solve(data):
    print(data["filepath"])
    filepath = data.get('filepath').replace("D:\\", "/mnt/d/").replace("C:\\", "/mnt/c/").replace("\\","/")
    print(filepath)
    flags = data.get('flags', [])

    if not filepath or not os.path.isfile(filepath):
        return jsonify({'error': f"Invalid file path '{filepath}'", "job_id":-1}), 400
    
    wcspath = join(config["SOLVE_DIR"], filepath.replace(".fits", ".wcs"))
    data["wcs"] = wcspath

    args = ['solve-field', filepath] + flags
    for key in data:
        if key not in ['filepath',"flags","fitspath"]:
            args.append(f'--{key}')
            args.append(str(data[key]))
        print(f"{key}: {data[key]}")
    print(args)
    job_id = create_record(filepath,wcspath," ".join(args))
    try:
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode != 0:
            mark_failed(job_id)
            return jsonify({'astrometry error': result.stderr, "job_id":job_id}), 500
        
        with fits.open(wcspath) as hdul:
            wcs_header = hdul[0].header

        fitspath = data.get("fitspath",filepath).replace("D:\\", "/mnt/d/").replace("C:\\", "/mnt/c/").replace("\\","/")

        with fits.open(fitspath, mode='update') as hdul:
            header = hdul[0].header
            for key in ["WCSAXES","CTYPE1","CTYPE2","EQUINOX","CRVAL1", "CRVAL2", "CRPIX1", "CRPIX2", "CUNIT1", "CUNIT2", "CD1_1", "CD1_2", "CD2_1", "CD2_2"]:
                header[key] = wcs_header[key]
        with open(join(logging_dir,f"astrom_{job_id}.log"),"w+") as f:
            f.write(result.stdout)
        print(f"Solved {filepath}")
        mark_solved(job_id)
        return jsonify({'message': 'Astrometry.net processing complete', "job_id":job_id}), 200
    except Exception as e:
        return jsonify({'error': str(e),"job_id":job_id}), 500

@app.route('/solve', methods=['POST'])
def solve():
    return _solve(request.get_json())

@app.route('/status', methods=['POST'])
def status():
    data = request.get_json()
    job_id = data.get("job_id")
    if job_id is None:
        return jsonify({'error': 'Missing job_id'}), 400
    cur.execute("SELECT * FROM astrometry WHERE id = ?",(job_id,))
    record = cur.fetchone()
    if record is None:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify({"status":record[4]})

@app.route('/log', methods=['POST'])
def log():
    data = request.get_json()
    job_id = data.get("job_id")
    if job_id is None:
        return jsonify({'error': 'Missing job_id'}), 400
    try:
        with open(join(logging_dir,f"astrom_{job_id}.log"),"r") as f:
            log = f.read()
    except FileNotFoundError:
        return jsonify({'error': 'Log not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify({"log":log})

@app.route("/jobs", methods=["GET"])
def jobs():
    cur.execute("SELECT * FROM astrometry")
    records = cur.fetchall()
    return jsonify({"jobs":records})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=config["PORT"])