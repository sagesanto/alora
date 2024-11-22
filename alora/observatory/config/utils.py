import os
import json
import logging
from pathlib import Path
import logging.config
from alora.observatory.config import logging_config_path

def configure_logger(name, outfile_path=None):
    # first, check if the logger has already been configured
    if logging.getLogger(name).hasHandlers():
        return logging.getLogger(name)
    try:
        with open(logging_config_path, 'r') as log_cfg:
            logging.config.dictConfig(json.load(log_cfg))
            logger = logging.getLogger(name)
            # set outfile of existing filehandler. need to do this instead of making a new handler in order to not wipe the formatter off
            # NOTE RELIES ON FILE HANDLER BEING THE SECOND HANDLER
            root_logger = logging.getLogger()
            if outfile_path is not None:
                file_handler = root_logger.handlers[1]
                file_handler.setStream(Path(outfile_path).open('a'))
            else:
                # remove the file handler
                root_logger.removeHandler(root_logger.handlers[1])
            try:
                os.remove("should_be_set_by_code.log")  # pardon this
            except:
                pass

    except Exception as e:
        print(f"Can't load logging config ({e}). Using default config.")
        logger = logging.getLogger(name)
        if outfile_path is not None:
            file_handler = logging.FileHandler(outfile_path, mode="a+")
            logger.addHandler(file_handler)

    # install_mp_handler()
    return logger