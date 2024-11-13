# Sage Santomenna 2024
# API for accessing observations and targets. requires access to Maestro db
import flask
from flask import request, jsonify, Flask
import os, logging, json
import logging.config
from sqlalchemy import text, not_
from sqlalchemy.exc import PendingRollbackError, IntegrityError, OperationalError
from datetime import datetime, UTC
import scheduleLib.db.dbConfig as dbConfig
from scheduleLib.db.db_models import Observation, CandidateModel, ProcessingCode
from flask_cors import CORS, cross_origin

with open("logging.json", 'r') as log_cfg:
    logging.config.dictConfig(json.load(log_cfg))
logger = logging.getLogger()
# set the out logfile to a new path
logger.handlers[0].baseFilename = os.path.join(os.path.dirname(__file__),"obs_logger.log")

db_session = dbConfig.dbSession

logger.info("Starting observation server")

app = Flask(__name__)
cors = CORS(app)
app.config['CORS_HEADERS'] = 'Content-Type'

def format_result(result):
    # Create a list of dictionaries, each representing a row
    rows = [dict(row._mapping) for row in result]
    return rows

# clumsy
def clean(query):
    # use an EXPLAIN statement to break the query down into VM instructions and examine the opcode column of the output. If the value "OpenWrite" occurs then the query is not read-only.
    r = db_session.execute(text(f"EXPLAIN {query}")).fetchall()
    for i in r:
        if "OpenWrite" in i[1] or "AutoCommit" in i[1]:
            return False
    return True

def test_obs_connection():
    try:
        db_session.execute(text("SELECT * FROM observation LIMIT 1"))
        return True, None
    except Exception as e:
        print(repr(e))
        logger.error("Request recieved but no observation database connection!")
        return False, jsonify({"result":"","error": "Internal error: no observation database connection when trying to answer request!"})

def test_target_connection():
    try:
        db_session.execute(text("SELECT * FROM Candidates LIMIT 1"))
        return True, None
    except Exception as e:
        print(repr(e))
        logger.error("Request recieved but no candidate database connection!")
        return False, jsonify({"result":"","error": "Internal error: no target database connection when trying to answer request!"})

@app.route("/targets/recent",methods=["GET"])
def recent_targets():
    status, msg = test_target_connection()
    if not status:
        return msg
    last_10 = db_session.query(CandidateModel).order_by(CandidateModel.DateAdded.desc()).limit(10).all()
    return {"error":"","result":[candidate.as_dict() for candidate in last_10]}

@app.route('/obs/recent',methods=["GET"])
def recent():
    status, msg = test_obs_connection()
    if not status:
        return msg
    last_10 = db_session.query(Observation).order_by(Observation.CaptureStartEpoch.desc()).limit(10).all()
    return {"error":"","result":[observation.as_dict() for observation in last_10]}

# NOTE: this will allow queries of the observation table as well as the targets table
@app.route('/targets/query',methods=["GET","POST"])
def targets_query():
    status, msg = test_target_connection()
    if not status:
        return msg
    try:
        logger.info(f"Received request.")
        try:
            data = request.get_json()
        except Exception as e:
            logger.error(f"Invalid JSON received: {repr(e)}")
            logger.error(f"Request data: {request.data}")
            return jsonify({"result": "", "error": "Invalid JSON received."})
        logger.info(f"Received data: {data}")

        if "query" not in data:
            logger.error("JSON did not contain 'query' key.")
            return jsonify({"result": "", "error": "JSON did not contain 'query' key."})
        error = ""
        try:
            q = data["query"]
            if clean(q):
                query_result = format_result(db_session.execute(text(q)))
            else:
                query_result = "Query is not read-only"
                error = "Query must be read-only"
                logger.critical(f"QUERY IS NOT READ ONLY: {q}")
            logger.info("Query complete.")
            return jsonify({"result":query_result,"error":error})
        except Exception as e:
            error = repr(e)
            logger.error(f"Error raised: {error}")
            print(e)
            return jsonify({"result":"","error": error})
    
    except Exception as e:
        logger.error(f"Error raised: {repr(e)}")
        return jsonify({"result":"","error": repr(e)})

# return all of the valid processing codes
@app.route('/obs/codes',methods=["GET"])
def codes():
    status, msg = test_target_connection()
    if not status:
        return msg
    last_10 = db_session.query(ProcessingCode).all()
    return {"error":"","result":[observation.as_dict() for observation in last_10]}

# this route allows updates to the observation table in the form of processing and submission codes
@app.route('/obs/update',methods=["POST"])
def update():
    status, msg = test_obs_connection()
    if not status:
        return msg
    try:
        logger.info(f"Received observation update.")
        try:
            data = request.get_json()
        except Exception as e:
            logger.error(f"Invalid JSON received: {repr(e)}")
            logger.error(f"Request data: {request.data}")
            return jsonify({"result": "", "error": "Invalid JSON received."})
        logger.info(f"Received data: {data}")

        # data should look like
        # {
        #     "update": [
        #         {"obs_id": 9, "processing_code": "test_processing_code", "submission_code": "test_submission_code", "comment": "test_comment"},
        #         {"obs_id": 21, "processing_code": "test_processing_code", "submission_code": "test_processing_code", "comment": ""}
        #     ]
        # }

        if "update" not in data:
            logger.error("JSON did not contain 'update' key.")
            return jsonify({"result": "", "error": "JSON did not contain 'update' key."})
        
        response_dict = {}
        # this is super primitive. later, we should consider doing validation (e.g. checking that the obs_id exists in the database, that they aren't updating the same obs twice, etc)
        for update in data["update"]:
            try:
                obs_id = update["obs_id"]
                processing_code = update["processing_code"]
                submission_code = update["submission_code"]
                obs = db_session.query(Observation).filter(Observation.ObservationID == obs_id).first()
                if obs is None:
                    response_dict[obs_id] = "observation does not exist"
                    logger.error(f"Observation {obs_id} does not exist.")
                    continue
                obs.Submitted = submission_code
                for code in [c for c in processing_code.split(",") if c]:
                        c = db_session.query(ProcessingCode).filter(ProcessingCode.Code == int(code)).first()
                        obs.ProcessingCode.append(c)
                if "comment" in update and update["comment"] != "":
                    obs.Comments = update["comment"]
                db_session.commit()
                response_dict[obs_id] = "updated"
                logger.info(f"Updated observation {obs_id} with processing code \"{processing_code}\", submission code \"{submission_code}\", and comment \"{update['comment']}\".")
            except (IntegrityError, OperationalError) as e:
                db_session.rollback()
                response_dict[obs_id] = repr(e)
                logger.error(f"Rolling back: db error raised when updating observation {obs_id}: {repr(e)}")
                print(e)
            except Exception as e:
                response_dict[obs_id] = repr(e)
                logger.error(f"Error raised when updating observation {obs_id}: {repr(e)}")
                print(e)
        return jsonify(response_dict)
    
    except Exception as e:
        logger.error(f"Error raised: {repr(e)}")
        return jsonify({"result":"","error": repr(e)})

# this route returns observations that need to have their status updated
@app.route('/obs/statusUnknown',methods=["GET"])
def process():
    status, msg = test_obs_connection()
    if not status:
        return msg
    try:
        # criteria: observation was made within the last 24 hrs, and both ProcessingCodes and Submitted are 0
        logger.info(f"Received request for observations with unknown status.")
        current_timestamp = datetime.now(UTC).timestamp()
        observations = db_session.query(Observation).filter(
            not_(Observation.ProcessingCode.any()),
            Observation.Submitted == 0,
            Observation.CaptureStartEpoch > current_timestamp - 86400
        ).all()
        # observations = db_session.query(Observation).filter(not_(Observation.ProcessingCode.any()), Observation.Submitted == 0).all
        query_result = [observation.as_dict() for observation in observations]
        return jsonify({"result":query_result,"error":""})
    except Exception as e:
        logger.error(f"Error raised: {repr(e)}")
        return jsonify({"result":"","error": repr(e)})

@app.route('/obs/query',methods=["GET","POST"])
def query():
    status, msg = test_obs_connection()
    if not status:
        return msg
    try:
        logger.info(f"Received observation query.")
        try:
            data = request.get_json()
        except Exception as e:
            logger.error(f"Invalid JSON received: {repr(e)}")
            logger.error(f"Request data: {request.data}")
            logger.error(e)
            return jsonify({"result": "", "error": "Invalid JSON received."})
        logger.info(f"Received data: {data}")

        if "query" not in data:
            logger.error("JSON did not contain 'query' key.")
            return jsonify({"result": "", "error": "JSON did not contain 'query' key."})
        error = ""
        try:
            q = data["query"]
            if clean(q):
                query_result = format_result(db_session.execute(text(q)))
            else:
                query_result = "Query is not read-only"
                error = "Query must be read-only"
                logger.critical(f"QUERY IS NOT READ ONLY: {q}")
            logger.info("Query complete.")
            return jsonify({"result":query_result,"error":error})
        except Exception as e:
            error = repr(e)
            logger.error(f"Error raised: {error}")
            print(e)
            return jsonify({"result":"","error": error})
    
    except Exception as e:
        logger.error(f"Error raised: {repr(e)}")
        return jsonify({"result":"","error": repr(e)})

# curl -X GET -H "Content-Type: application/json" -d "{\"query\":\"SELECT * FROM observation LIMIT 5\"}" "http://localhost:5010/obs/query"

if __name__ == "__main__":
    app.run(port=5010,debug=True)
