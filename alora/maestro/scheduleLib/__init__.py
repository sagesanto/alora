from os.path import join, abspath, dirname
__all__ = ["schedule", "asyncUtils", "genUtils", "candidateDatabase","module_loader"]

CANDIDATE_SCHEMA_PATH = join(abspath(dirname(__file__)), "candidate_schema.json")