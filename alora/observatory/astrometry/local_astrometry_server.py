import os
from os.path import join, dirname, abspath, basename, splitext
import subprocess
import tomlkit
import sqlite3
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
import numpy as np
from threading import Thread, Event
import queue, threading
from astropy.io import fits
from astropy.table import Table
from astropy.coordinates import SkyCoord, Angle
import astropy.units as u
from datetime import datetime
import numpy as np
import tomlkit
import sqlite3
from alora.astroutils import calc_mean_fwhm, source_catalog
from alora.config import config, configure_logger, logging_dir

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

logger = configure_logger("Astrometry",join(logging_dir,"astrometry.log"))

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

astrom_logging_dir = abspath(join(dirname(abspath(__file__)),"logs"))

os.makedirs(astrom_logging_dir,exist_ok=True)
os.makedirs(acfg["SOLVE_DIR"],exist_ok=True)

app = Flask(__name__)
sio = SocketIO(app)

def create_record(filepath,flags):
    with lock: 
        conn,cur = connect_to_db()
        cur.execute("INSERT INTO astrometry (filepath, flags, status) VALUES (?,?,?)",(filepath,flags,"queued"))
        conn.commit()
        cur.execute("SELECT last_insert_rowid()")
        res= cur.fetchone()[0]
        conn.close()
        return res
    
def set_args(record_id,args):
    with lock:
        conn,cur = connect_to_db()
        cur.execute("UPDATE astrometry SET flags = ? WHERE id = ?",(args,record_id))
        conn.commit()
        conn.close()

def mark_status(record_id,status):
    with lock:
        conn,cur = connect_to_db()
        cur.execute("UPDATE astrometry SET status = ? WHERE id = ?",(status, record_id,))
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

def notify(job_id,status, status_msg):
    mark_status(job_id,status)
    set_status_message(job_id,status_msg)
    with lock:
        sio.emit("job_finished",{"job_id":job_id,"status":status})


def solver(stop_event):
    while True:
        if stop_event.is_set():
            return
        try:
            event = solve_queue.get(timeout=0.1)
        except queue.Empty:
            continue
    
        filepath = event.pop("filepath")
        job_id = event.pop("job_id")
        logger.info(f"Solving {filepath} (job {job_id})")
        logger.info(f"{len(solve_queue.queue)} jobs remaining in queue")
        try:
            if not filepath or not os.path.isfile(filepath):
                logger.error(f"File not found: {filepath}")
                notify(job_id,"crashed",f"file not found: '{filepath}'")
                continue

            mark_status(job_id,"processing")

            if event.pop("do_source_extraction"):
                with fits.open(filepath) as hdul:
                    data = hdul[0].data

                logger.info("Making source catalog...")
                cat = make_source_cat(data)
                if ".fits" in filepath:
                    newpath = filepath.replace(".fits", ".cat")
                else:
                    newpath = filepath.replace(".fit", ".cat")

                cat.write(newpath, format='fits', overwrite=True)

                event["width"] = data.shape[1]
                event["height"] = data.shape[0]
                event["x-column"] = "xcentroid"
                event["y-column"] = "ycentroid"
                event["fitspath"] = filepath  # specify the fits path that the sol will be written into, even tho the actual file the solution is derived from is a catalog
                event["filepath"] = newpath    
                filepath = newpath

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
                logger.debug(f"{key}: {event[key]}")
            
            set_args(job_id," ".join(args))
            logger.debug(args)
            logger.info("Solving...")
            result = subprocess.run(args=args, capture_output=True, text=True)
            if result.returncode != 0:
                err = result.stderr
                notify(job_id,"crashed","Astrometry error: "+err)
                logger.error("Astrometry error: "+ err)
                with open(join(astrom_logging_dir,f"astrom_{job_id}.log"),"w+") as f:
                    f.write(result.stderr)
                continue

            if os.path.exists(solpath):
                logger.info(f"Solved {filepath}")
                with fits.open(wcspath) as hdul:
                    wcs_header = hdul[0].header

                fitspath = event.get("fitspath",filepath)

                with fits.open(fitspath, mode='update') as hdul:
                    header = hdul[0].header
                    for key in ["WCSAXES","CTYPE1","CTYPE2","EQUINOX","CRVAL1", "CRVAL2", "CRPIX1", "CRPIX2", "CUNIT1", "CUNIT2", "CD1_1", "CD1_2", "CD2_1", "CD2_2"]:
                        header[key] = wcs_header[key]
                with open(join(astrom_logging_dir,f"astrom_{job_id}.log"),"w+") as f:
                    f.write(result.stdout)
                notify(job_id,"solved","Astrometry.net successfully solved the field.")
                continue
            else:
                logger.error(f"Failed to solve {filepath}")
                notify(job_id,"failed","Astrometry.net did not find a solution")
                continue
        except Exception as e:
            logger.error("Alora Astrom server exception: "+str(e))
            logger.exception(e)
            if job_id != -1:
                notify(job_id,"crashed","Alora Astrom server exception: "+str(e))
            continue


@app.route('/solve', methods=['POST'])
def solve():
    # make record here
    r = request.get_json()
    job_id = create_record(r["filepath"],"")
    r["job_id"] = job_id
    r["do_source_extraction"] = False
    logger.info(f"Queueing job {job_id}: {r['filepath']}")
    solve_queue.put(r)
    return jsonify({"job_id":job_id})

@app.route("/cat_and_solve",methods=["POST"])
def cat_and_solve():
    r = request.get_json()
    job_id = create_record(r["filepath"],"")
    r["job_id"] = job_id
    r["do_source_extraction"] = True
    logger.info(f"Queueing job {job_id}: {r['filepath']}")
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
        with open(join(astrom_logging_dir,f"astrom_{job_id}.log"),"r") as f:
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

@app.route("/show",methods=["GET"])
def show():
    with lock:
        conn, cur = connect_to_db()
        cur.execute("SELECT id, filepath, status, status_msg, created_at FROM astrometry ORDER BY created_at DESC")
        records = cur.fetchall()
        conn.close()
        html_content = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Astrometry Job Results</title>
            <style>
                table {
                    width: 100%;
                    border-collapse: collapse;
                }
                th, td {
                    border: 1px solid #ddd;
                    padding: 8px;
                    text-align: left;
                }
                th {
                    background-color: #f2f2f2;
                }
                .processing {
                    background-color: lightblue;
                }
                .failed {
                    background-color: lightcoral;
                }
                .crashed {
                    background-color: darkred;
                    color: white;
                }
                .solved {
                    background-color: lightgreen;
                }
                .queued {
                    background-color: gray;
                    color: white;
                }
            </style>
        </head>
        <body>
            <h1>Astrometry Job Results</h1>
            <table>
                <tr>
                    <th>Job ID</th>
                    <th>Date Requested</th>
                    <th>Filepath</th>
                    <th>Status</th>
                    <th>Status Message</th>
                </tr>
        """

        for record in records:
            job_id, filepath, status, status_msg, created_at = record
            created_at = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
            created_at_str = created_at.strftime('%Y-%m-%d %H:%M:%S')
            html_content += f"""
                <tr class="{status}">
                    <td>{job_id}</td>
                    <td>{created_at_str}</td>
                    <td>{filepath}</td>
                    <td>{status.capitalize()}</td>
                    <td>{status_msg}</td?
                </tr>
            """

        html_content += """
            </table>
        </body>
        </html>
        """
        return html_content


if __name__ == '__main__':
    stop_event = Event()        
    solver_thread = Thread(target=solver, args=(stop_event,))
    solver_thread.start()
    logger.info(f'Starting Astrometry server on port {acfg["PORT"]}')
    sio.run(app, host='127.0.0.1', port=acfg["PORT"])
    logger.info('Shutting down...')
    stop_event.set()
    solver_thread.join()