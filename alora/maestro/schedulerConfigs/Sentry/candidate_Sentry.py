import sys, os, json
from os.path import abspath, dirname, join, pardir

MAESTRO_PATH = abspath(join(dirname(__file__),pardir,pardir))
module_path = abspath(dirname(__file__))

sys.path.append(MAESTRO_PATH)
from scheduleLib.genUtils import generate_candidate_class
from scheduleLib.candidateDatabase import BaseCandidate

SentryCandidate = generate_candidate_class('Sentry', {}, {}, {}, BaseCandidate)