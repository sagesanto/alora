# Sage Santomenna 2024
# the observer takes incoming observation requests and observes them in order. 
# it is meant to run as a continuous service that has a monopoly on telescope and dome movement.
# i am not yet sure how much decision making about targets the observer will do, or how exactly it will interface with the database

from alora import Observatory
import sys, os, logging
import queue, threading
import json, requests, socket
from flask import request, jsonify, Flask
from threading import Thread, Event

from .data_archive import Observation

observation_queue = queue.Queue()
lock = threading.Lock()

def observer(stop_signal):
    to_observe = []
    while True:
        if stop_signal.is_set():
            return
        try:
            event = event_queue.get(timeout=0.5)
        except queue.Empty:
            continue


stop_event = Event()