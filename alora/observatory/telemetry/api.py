from flask import Flask, request, jsonify
import flask
import logging
import logging.handlers
import rpyc, os
from .utils import init_logger, read_json
from datetime import datetime
import time, hashlib, hmac, base64
from .config import telem_log_dir

logger = init_logger(os.path.join(telem_log_dir,"api.log"))[0]

from alora.observatory.config import config as cfg

telem_port = int(cfg['TELEMETRY_PORT'])
host_port = (cfg['TELEM_API_PORT'])
telemetry_conn = None

app = Flask(__name__)

def time_to_str(time):
    print(time)
    time = float(time)
    if time > 1000000000:
        time = time/1000 # lol
    print(type(time))
    print(time)
    t =datetime.fromtimestamp(time)
    print(t)
    t = t.strftime('%Y-%m-%d %H:%M:%S')
    print(t)
    return t


@app.route('/api', methods=['GET'])
def api():
    if telemetry_conn is None:
        logger.error("No telemetry connection!")
        return jsonify({"result":"","error": "No telemetry connection when trying to answer data request!"})
    try:
        logger.info(f"Received request.")
        
        try:
            data = request.get_json()
        except Exception as e:
            logger.error(f"Invalid JSON received: {repr(e)}")
            return jsonify({"result": "", "error": "Invalid JSON received."})
        logger.info(f"Received data: {data}")

        if "query" not in data:
            logger.error("JSON did not contain 'query' key.")
            return jsonify({"result": "", "error": "JSON did not contain 'query' key."})
        
        query_result, error = telemetry_conn.root.sql_query(data["query"])
        return jsonify({"result":query_result,"error":error})
    
    except Exception as e:
        logger.error(f"Error raised: {repr(e)}")
        return jsonify({"result":"","error": repr(e)})

@app.route('/api/blueprint', methods=['GET'])
def blueprint():
    if telemetry_conn is None:
        logger.error("No telemetry connection!")
        return jsonify({"result":"","error": "No telemetry connection when trying to fetch blueprints!"})
    try:
        logger.info(f"Received request for blueprint.")
        blueprint = telemetry_conn.root.blueprint
        return jsonify({"result":blueprint,"error":""})
    except Exception as e:
        logger.error(f"Error raised: {repr(e)}")
        return jsonify({"result":"","error": repr(e)})

@app.route('/weather', methods=['GET'])
def weather():
    if telemetry_conn is None:
        logger.error("No telemetry connection when trying to fetch weather!")
        return jsonify({"result":"","error": "No telemetry connection!"})
    weather_data = telemetry_conn.root.sql_query("SELECT * FROM Weather ORDER BY Timestamp DESC LIMIT 1")[0][0]
    print("weather data:",weather_data)
    return jsonify({
        'error': '',
        'result': weather_data
    })

@app.route('/api/status', methods=['GET'])
def status():
    sensor_status = telemetry_conn.root.sql_query("SELECT * FROM SensorUptime ORDER BY Timestamp DESC LIMIT 1")[0][0]
    return jsonify({
        'error': '',
        'result': sensor_status
    })



if __name__ == "__main__":
    logger.info("Starting API server")
    telemetry_conn = rpyc.connect('localhost', telem_port)
    # print(telemetry_conn.root.sql_query("SELECT * FROM SensorUptime"))
    app.run(port=host_port,debug=True)