import logging, os, json, sys
from datetime import datetime
import queue
import logging.handlers
from alora.config import configure_logger


def get_timestamp():
    return datetime.utcnow().timestamp()

def reify_dict(remote_dict_items: dict):
    # print(remote_dict_items)
    return {key: val for key, val in remote_dict_items}

def init_logger(filepath,formatter=None):
    # queueing is for thread safety
    logger = configure_logger(__name__,filepath)
    # if formatter is None:
    #     dateFormat = '%m/%d/%Y %H:%M:%S'
    #     LOGFORMAT = " %(asctime)s %(log_color)s%(levelname)-5s%(reset)s | %(log_color)s%(message)s%(reset)s"
    #     formatter = ColoredFormatter(LOGFORMAT, datefmt=dateFormat,
    #                                 log_colors={
    #                                     'DEBUG':    'white',
    #                                     'INFO':     'white',
    #                                     'WARNING':  'yellow',
    #                                     'ERROR':    'red',
    #                                     'CRITICAL': 'red,bg_white',},)
    log_queue = queue.Queue(-1)
    queue_handler = logging.handlers.QueueHandler(log_queue)
    
    # fileHandler = logging.FileHandler(os.path.abspath(filepath))
    # fileHandler.setFormatter(formatter)

    # streamHandler = logging.StreamHandler(sys.stdout)
    # streamHandler.setFormatter(formatter)
    # queue_listener = logging.handlers.QueueListener(log_queue, fileHandler, streamHandler)
    queue_listener = logging.handlers.QueueListener(log_queue, *logger.handlers)
    logger.addHandler(queue_handler)
    logger.setLevel(logging.INFO)
    # start the listener thread
    queue_listener.start()

    return logger, queue_listener

def read_json(jstring: str):
    d = {}
    try:
        d = json.loads(jstring)
        return d
    except Exception as e:
        raise ValueError(f"couldn't read json from string '{jstring}': {repr(e)}") from e