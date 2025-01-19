# Sage Santomenna 2025

import sys, os, logging
from os.path import join, dirname, abspath, basename, splitext
from abc import ABC, abstractmethod
import queue, threading
import json, requests, socket
from flask import request, jsonify, Flask
from threading import Thread, Event
import subprocess
import sqlite3
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
import numpy as np
from datetime import datetime
import numpy as np
import sqlite3
from astropy.io import fits
from astropy.table import Table
from astropy.coordinates import SkyCoord, Angle
import astropy.units as u
from pytz import UTC

from alora.config import config

from sagelib.pipeline import configure_db
from sagelib.pipeline.bin.product_info import product_info

db_path = join(dirname(abspath(__file__)), "archive.db")
db = configure_db(db_path)
from alora.config import config, configure_logger, logging_dir

logger = configure_logger("Archive",join(logging_dir,"archive.log"))
app = Flask(__name__)
sio = SocketIO(app)

socket_conns = []
socket_lock = threading.Lock()

# db_lock = threading.Lock()
# FUCK i would be astounded if i managed to make PipelineDB threadsafe
# need another worker thread probably

@app.route("/status",methods=["GET"])
def status():
    return jsonify({"status":"ok"}),200

@app.route("/listen",methods=["GET"])
def listen():
    raise NotImplementedError()

@app.route("/query",methods=["POST"])
def query():
    with db_lock:
        q = request.json["query"]
    # parse request 
    # clean - use VM to look for SQL modify operations, abort if found
    # serialize response

@app.route("/recent",methods=["GET"])
def recent():
    with db_lock:

    # just get like the n most recent additions to the archive 
        # don't include derived products
    pass

@app.route("/start_watching_dir",methods=["POST"])
def start_watching_dir():
    # given some params, start watchdog on given dir to create new archive entries on file creation event
    pass

@app.route("/stop_watching_dir",methods=["POST"])
def stop_watching_dir():
    # this is obvious
    pass

@app.route("/update/<id>",methods=["POST"])
def update(id):
    pass

@app.route("/info/<id>",methods=["GET"])
def info(id):
    try:
        return product_info(id), 200
    except ValueError as e:
        return str(e), 500

@app.route("/create",methods=["POST"])
def create():
    # christ
    pass



