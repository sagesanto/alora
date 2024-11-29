# Sage Santomenna 2024
# many voices joined in song

import sys, os, logging
from os.path import join
import queue, threading
import json, requests, socket
from flask import request, jsonify, Flask
from configparser import ConfigParser
from threading import Thread, Event
from datetime import datetime, UTC

from alora.observatory.config import config as cfg, configure_logger, logging_dir

app = Flask(__name__)
notification_queue = queue.Queue()
subscribers = {}
subscribed_to = {}
lock = threading.Lock()

severity_levels = ["info","warning","error","critical"]

logger = configure_logger("choir",join(logging_dir,"choir.log"))

@app.route('/subscribe', methods=['POST'])
def subscribe():
    subscriber = request.json["webhook_url"]
    subscribed_severity = request.json["severity"]
    print(subscribed_severity)
    name = request.json["name"]
    with lock:
        # subscribe to all severities at or above the level requested
        severities = [severity_levels[i] for i in range(len(severity_levels)) if i >= dict(zip(severity_levels,list(range(len(severity_levels)))))[subscribed_severity]]
        for severity in severities:
            if severity not in subscribers:
                subscribers[severity] = []
            subscribers[severity].append(subscriber)
            subscribers[severity] = list(set(subscribers[severity]))
        if subscriber not in subscribed_to:
            subscribed_to[subscriber] = []
        subscribed_to[subscriber].extend(severities)
        subscribed_to[subscriber] = list(set(subscribed_to[subscriber]))
    print(f"Got subscription request from {name} ({subscriber}) for severity levels {severities}")
    print(f"Subscribers: {subscribers}")
    return jsonify({'status': 'success'})

@app.route('/unsubscribe', methods=['POST'])
def unsubscribe():
    subscriber = request.json["webhook_url"]
    with lock:
        for subscribed_severity in subscribed_to[subscriber]:
            del subscribers[subscribed_severity]
        del subscribed_to[subscriber]
    return jsonify({'status': 'success'})

@app.route('/health', methods=['GET'])
def health():
    with lock:
        return jsonify({'status': 'healthy','subscribers':subscribers})

@app.route("/notify", methods=["POST"])
def notify():
    source = request.json["source"]
    topic = request.json["topic"]
    severity = request.json["severity"]
    msg = request.json["msg"]
    if severity not in severity_levels:
        logger.warning(f"recieved invalid severity '{severity}' from source '{source}'")
        return jsonify({'status':'error','message':f'severity must be one of {severity_levels}'})
    logger.info(f"recieved {severity} notification from {source} on topic {topic}: {msg}")
    notification_queue.put({"source":source,"topic":topic,"severity":severity,"msg":msg,"timestamp":datetime.now(tz=UTC).strftime('%Y-%m-%d %H:%M:%S UTC')})
    return jsonify({'status':'success'})

def publish(stop_event):
    # continually
    while True:
        if stop_event.is_set():
            return
        try:
            event = notification_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        notify_subscribers(event)

def notify_subscribers(event):
    logger.info(f"Notifying subscribers of event: {event}")
    with lock:
        for subscriber in subscribers.get(event['severity'], []):
            try:
                requests.post(subscriber, json=event)
            except Exception as e:
                logger.error(f"Failed to notify subscriber {subscriber['url']}: {e}")

def is_port_available(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) != 0

def find_available_port(start_port, end_port):
    for port in range(start_port, end_port):
        if is_port_available(port):
            return port
    return None

if __name__ == "__main__":
    port = cfg['CHOIR_PORT']

    logger.info('Starting publisher thread')
    stop_event = Event()        
    publish_thread = Thread(target=publish, args=(stop_event,))
    publish_thread.start()
    logger.info('Starting notification server on port %d', port)
    app.run(port=port)
    logger.info('Shutting down...')
    stop_event.set()
    publish_thread.join()
    logger.info('Publisher stopped')
    logger.info('All done!')