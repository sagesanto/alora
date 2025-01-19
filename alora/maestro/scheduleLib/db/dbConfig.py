# Sage Santomenna 2023, 2025
# SQLAlchemy database connection and configuration
import json
import logging
import os
from os.path import abspath, dirname, join

from sqlalchemy import create_engine
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker, registry
from alora.config import configure_logger

# @event.listens_for(Engine, "before_cursor_execute")
# def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
#     conn.info.setdefault("query_start_time", []).append(time.time())
#     logger.debug("Start Query: %s", statement)
#
#
# @event.listens_for(Engine, "after_cursor_execute")
# def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
#     total = time.time() - conn.info["query_start_time"].pop(-1)
#     logger.debug("Query Complete!")
#     logger.debug("Total Time: %f", total)


# @event.listens_for(Engine, 'close')
# def receiveClose(dbapi_connection, connection_record):
#     cursor = dbapi_connection.cursor()
#     # cursor.execute("PRAGMA analysis_limit=400")
#     # cursor.execute("PRAGMA optimize")


@event.listens_for(Engine, "connect")
def setSQLitePragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode = MEMORY")
    cursor.execute("PRAGMA synchronous = OFF")
    cursor.execute("PRAGMA temp_store = MEMORY")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# def renewDbSession():
#     global dbSession  # man this is bad
#     dbSession.expire_all()
#     dbSession.close()
#     dbSession = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine, ))
#     logger.info("Renewed db session")


mapper_registry = registry()
candidate_base = mapper_registry.generate_base()

def configure_db(dbpath:str):
    """Connect to a candidate database 

    :param dbpath: filepath of database
    :type dbpath: str
    :return: a candidate database session that can be used to interact with the database, and the candidate engine.
    :rtype: Tuple(sqlalchemy.orm.Session, sqlalchemy.engine.Engine)
    """
    logger = configure_logger('DB Config', join(dirname(dbpath),"db_config.log"))

    logger.info("Db Configuration Started")
    SQLALCHEMY_DATABASE_URL = f'sqlite:///{dbpath}'

    candidate_engine = create_engine(SQLALCHEMY_DATABASE_URL)  # , echo="debug")
    candidate_autocommit_engine = candidate_engine.execution_options(isolation_level="AUTOCOMMIT")

    candidate_db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=candidate_engine))
    candidate_read_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=candidate_engine))
    candidate_base.query = candidate_db_session.query_property()

    logger.info("Candidate Db Session Created")
    return candidate_db_session, candidate_engine