import sys, os, json
from os.path import abspath, dirname, join, pardir


MAESTRO_PATH = abspath(join(dirname(__file__),pardir,pardir))
module_path = abspath(dirname(__file__))

sys.path.append(MAESTRO_PATH)
from alora.maestro.scheduleLib.genUtils import generate_candidate_class
from alora.maestro.scheduleLib.candidateDatabase import BaseCandidate, construct_quantity, serialize_quantity

aphot_field_constructors = {"quantity":construct_quantity}
aphot_field_serializers = {"quantity":serialize_quantity}

with open(join(module_path,"aphot_schema.json"), "r") as f:
    aphot_candidate_schema = json.load(f)
   
AphotCandidate = generate_candidate_class('Astrophotography', aphot_field_constructors, aphot_field_serializers, aphot_candidate_schema, BaseCandidate)