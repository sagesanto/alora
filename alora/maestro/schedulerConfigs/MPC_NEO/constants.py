import os

CACHE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "cache"))
CACHE_DB_PATH = os.path.join(CACHE_PATH, "cache.db")