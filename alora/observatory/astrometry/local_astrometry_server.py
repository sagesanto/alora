import os
from os.path import join, dirname, abspath, basename, splitext
import subprocess
import tomlkit
import sqlite3
from flask import Flask, request, jsonify
import numpy as np
from threading import Thread, Event
import queue, threading
from astropy.io import fits
from astropy.table import Table
from astropy.coordinates import SkyCoord, Angle
import astropy.units as u
import numpy as np
import tomlkit
import sqlite3
from alora.astroutils import calc_mean_fwhm, source_catalog
from alora.config import config

import warnings
warnings.filterwarnings('ignore', module="astropy.io.fits.card")
warnings.filterwarnings('ignore', module="astropy.io.fits.convenience")
warnings.filterwarnings('ignore', module="photutils.segmentation.deblend")

def make_source_cat(data:np.ndarray):
    mean_fwhm = calc_mean_fwhm(data)
    cat = source_catalog(data,source_sigma=3,ncont=5,fwhm_pix=mean_fwhm)
    return cat["xcentroid","ycentroid"]

db_path = join(dirname(abspath(__file__)), "astrom.db")
conn = sqlite3.connect(db_path)
cur = conn.cursor()

solve_queue = queue.Queue()
lock = threading.Lock()


cur.execute("CREATE TABLE IF NOT EXISTS astrometry (id INTEGER PRIMARY KEY AUTOINCREMENT, filepath TEXT, flags TEXT, status TEXT, status_msg TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
conn.commit()
conn.close()

acfg = config["ASTROMETRY"]

def connect_to_db():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    return conn, cur

logging_dir = abspath(join(dirname(abspath(__file__)),"logs"))

os.makedirs(logging_dir,exist_ok=True)
os.makedirs(acfg["SOLVE_DIR"],exist_ok=True)

app = Flask(__name__)

def create_record(filepath,wcspath,flags):
    with lock: 
        conn,cur = connect_to_db()
        cur.execute("INSERT INTO astrometry (filepath, wcs, flags, status) VALUES (?,?,?,?)",(filepath,wcspath,flags,"queued"))
        conn.commit()
        cur.execute("SELECT last_insert_rowid()")
        res= cur.fetchone()[0]
        conn.close()
        return res
    
def set_args(record_id,args):
    with lock:
        conn,cur = connect_to_db()
        cur.execute("UPDATE astrometry SET args = ? WHERE id = ?",(args,record_id))
        conn.commit()
        conn.close()

def mark_processing(record_id):
    with lock:
        conn,cur = connect_to_db()
        cur.execute("UPDATE astrometry SET status = 'processing' WHERE id = ?",(record_id,))
        conn.commit()
        conn.close()

def mark_solved(record_id):
    with lock:
        conn,cur = connect_to_db()
        cur.execute("UPDATE astrometry SET status = 'solved' WHERE id = ?",(record_id,))
        conn.commit()
        conn.close()

def mark_failed(record_id):
    with lock:
        conn,cur = connect_to_db()
        cur.execute("UPDATE astrometry SET status = 'failed' WHERE id = ?",(record_id,))
        conn.commit()
        conn.close()

def set_status_message(record_id,msg):
    with lock:
        conn,cur = connect_to_db()
        cur.execute("UPDATE astrometry SET status_msg = ? WHERE id = ?",(msg,record_id))
        conn.commit()
        conn.close()

# TODO: make this more rigorous (not just C and D drives lol)
def wpath_to_wsl(windows_path):
    return windows_path.replace("D:\\", "/mnt/d/").replace("C:\\", "/mnt/c/").replace("\\","/")

def unpack_args(req_dict):
    args = []
    for key in req_dict:
        if key not in ['filepath',"flags","fitspath"]:
            args.append(f'--{key}')
            args.append(str(req_dict[key]))
    return args

def solver(stop_event):
    while True:
        if stop_event.is_set():
            return
        try:
            event = solve_queue.get(timeout=0.1)
        except queue.Empty:
            continue
    
        filepath = event.pop("filepath")
        wcspath = event.pop("wcs")
        job_id = event.pop("job_id")
        print(f"Solving {filepath} (job {job_id})")
        print(f"{len(solve_queue.queue)} jobs remaining in queue")
        try:
            if not filepath or not os.path.isfile(filepath):
                with lock:
                    mark_failed(job_id)
                continue

            with lock:
                mark_processing(job_id)

            if event.pop("do_source_cat"):
                with fits.open(filepath) as hdul:
                    data = hdul[0].data

                print("Making source catalog...")
                cat = make_source_cat(data)
                if ".fits" in filepath:
                    newpath = filepath.replace(".fits", "_cat.fits")
                else:
                    newpath = filepath.replace(".fit", "_cat.fits")

                cat.write(newpath, format='fits', overwrite=True)
                # print("cat path:",newpath)

                event["width"] = data.shape[1]
                event["height"] = data.shape[0]
                event["x-column"] = "xcentroid"
                event["y-column"] = "ycentroid"
                event["fitspath"] = filepath  # specify the fits path that the sol will be written into, even tho the actual file the solution is derived from is a catalog
                event["filepath"] = newpath    

            flags = event.get('flags', [])
            
            solve_dir = abspath(acfg["SOLVE_DIR"])

            wcspath = join(solve_dir, basename(splitext(filepath)[0]+".wcs"))
            event["wcs"] = wpath_to_wsl(wcspath)

            # solpath is a path to a file that astrometry will create to indicate that solving succeeded
            solpath = join(solve_dir,basename(splitext(filepath)[0]+".solved"))
            event["solved"] = wpath_to_wsl(solpath)
            
            event["dir"] = wpath_to_wsl(solve_dir)

            args = ["wsl","solve-field",wpath_to_wsl(filepath)] + flags
            for key in event:
                if key not in ['filepath',"flags","fitspath"]:
                    args.append(f'--{key}')
                    args.append(str(event[key]))
                print(f"{key}: {event[key]}")
            
            set_args(job_id," ".join(args))
            print(args)
            print("Solving...")
            result = subprocess.run(args=args, capture_output=True, text=True)
            if result.returncode != 0:
                mark_failed(job_id)
                err = result.stderr
                print("Astrometry error: ", err)
                set_status_message(job_id,"Astrometry error: "+err)
                with open(join(logging_dir,f"astrom_{job_id}.log"),"w+") as f:
                    f.write(result.stderr)
                continue
                # return jsonify({'astrometry error': result.stderr, "job_id":job_id,"success":False}), 500
            
            with fits.open(wcspath) as hdul:
                wcs_header = hdul[0].header

            fitspath = event.get("fitspath",filepath)

            with fits.open(fitspath, mode='update') as hdul:
                header = hdul[0].header
                for key in ["WCSAXES","CTYPE1","CTYPE2","EQUINOX","CRVAL1", "CRVAL2", "CRPIX1", "CRPIX2", "CUNIT1", "CUNIT2", "CD1_1", "CD1_2", "CD2_1", "CD2_2"]:
                    header[key] = wcs_header[key]
            with open(join(logging_dir,f"astrom_{job_id}.log"),"w+") as f:
                f.write(result.stdout)
            if os.path.exists(solpath):
                print(f"Solved {filepath}")
                mark_solved(job_id)
                set_status_message(job_id,"Astrometry.net successfully solved the field.")
                continue
                # return jsonify({'message': 'Astrometry.net processing complete', "job_id":job_id, "success":True}), 200
            else:
                print(f"Failed to solve {filepath}")
                mark_failed(job_id)
                set_status_message(job_id,"Astrometry.net did not find a solution.")
                # return jsonify({'message': 'Astrometry.net did not find a solution', "job_id":job_id, "success":False}), 201
                continue
        except Exception as e:
            print("Alora Astrom server exception: ",str(e))
            if job_id != -1:
                mark_failed(job_id)
                set_status_message(job_id,"Alora Astrom server exception: "+str(e))
            continue
            # return jsonify({'error': str(e),"job_id":job_id,"success":False}), 500


# def _solve(data):
#     job_id = -1
#     try:
#         filepath = data["filepath"]
#         print(filepath)
#         flags = data.get('flags', [])

#         if not filepath or not os.path.isfile(filepath):
#             return jsonify({'error': f"Invalid file path '{filepath}'", "job_id":-1,"success":False}), 400
        
#         solve_dir = abspath(acfg["SOLVE_DIR"])

#         wcspath = join(solve_dir, basename(splitext(filepath)[0]+".wcs"))
#         data["wcs"] = wpath_to_wsl(wcspath)

#         # solpath is a path to a file that astrometry will create to indicate that solving succeeded
#         solpath = join(solve_dir,basename(splitext(filepath)[0]+".solved"))
#         data["solved"] = wpath_to_wsl(solpath)
        
#         data["dir"] = wpath_to_wsl(solve_dir)

#         args = ["wsl","solve-field",wpath_to_wsl(filepath)] + flags
#         for key in data:
#             if key not in ['filepath',"flags","fitspath"]:
#                 args.append(f'--{key}')
#                 args.append(str(data[key]))
#             print(f"{key}: {data[key]}")
        
#         job_id = create_record(filepath,wcspath," ".join(args))
#         print(args)
#         result = subprocess.run(args=args, capture_output=True, text=True)
#         if result.returncode != 0:
#             mark_failed(job_id)
#             return jsonify({'astrometry error': result.stderr, "job_id":job_id,"success":False}), 500
        
#         with fits.open(wcspath) as hdul:
#             wcs_header = hdul[0].header

#         fitspath = data.get("fitspath",filepath)

#         with fits.open(fitspath, mode='update') as hdul:
#             header = hdul[0].header
#             for key in ["WCSAXES","CTYPE1","CTYPE2","EQUINOX","CRVAL1", "CRVAL2", "CRPIX1", "CRPIX2", "CUNIT1", "CUNIT2", "CD1_1", "CD1_2", "CD2_1", "CD2_2"]:
#                 header[key] = wcs_header[key]
#         with open(join(logging_dir,f"astrom_{job_id}.log"),"w+") as f:
#             f.write(result.stdout)
#         if os.path.exists(solpath):
#             print(f"Solved {filepath}")
#             mark_solved(job_id)
#             return jsonify({'message': 'Astrometry.net processing complete', "job_id":job_id, "success":True}), 200
#         else:
#             mark_failed(job_id)
#             print(f"Failed to solve {filepath}")
#             return jsonify({'message': 'Astrometry.net did not find a solution', "job_id":job_id, "success":False}), 201

#     except Exception as e:
#         if job_id != -1:
#             mark_failed(job_id)
#         return jsonify({'error': str(e),"job_id":job_id,"success":False}), 500

@app.route('/solve', methods=['POST'])
def solve():
    # make record here
    r = request.get_json()
    job_id = create_record(r["filepath"],"","")
    r["job_id"] = job_id
    r["do_source_extraction"] = False
    solve_queue.put(r)
    return jsonify({"job_id":job_id})

@app.route("/cat_and_solve",methods=["POST"])
def cat_and_solve():
    r = request.get_json()
    job_id = create_record(r["filepath"],"","")
    r["job_id"] = job_id
    r["do_source_extraction"] = True
    solve_queue.put(r)
    return jsonify({"job_id":job_id})

@app.route('/status', methods=['POST'])
def status():
    data = request.get_json()
    job_id = data.get("job_id")
    if job_id is None:
        return jsonify({'error': 'Missing job_id'}), 400
    conn,cur = connect_to_db()
    cur.execute("SELECT * FROM astrometry WHERE id = ?",(job_id,))
    record = cur.fetchone()
    conn.close()
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
    conn,cur = connect_to_db()
    cur.execute("SELECT * FROM astrometry")
    records = cur.fetchall()
    conn.close()
    return jsonify({"jobs":[dict(r) for r  in records]})

if __name__ == '__main__':
    stop_event = Event()        
    solver_thread = Thread(target=solver, args=(stop_event,))
    solver_thread.start()
    print(f'Starting Astrometry server on port {acfg["PORT"]}')
    app.run(host='0.0.0.0', port=acfg["PORT"],debug=True)
    print('Shutting down...')
    stop_event.set()
    solver_thread.join()