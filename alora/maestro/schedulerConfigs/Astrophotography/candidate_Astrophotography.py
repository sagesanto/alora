import sys, os, json
from os.path import abspath, dirname, join, pardir


MAESTRO_PATH = abspath(join(dirname(__file__),pardir,pardir))
module_path = abspath(dirname(__file__))

sys.path.append(MAESTRO_PATH)
from scheduleLib.genUtils import generate_candidate_class
from scheduleLib.candidateDatabase import BaseCandidate, construct_quantity, serialize_quantity

aphot_field_constructors = {"quantity":construct_quantity}
aphot_field_serializers = {"quantity":serialize_quantity}

with open(join(module_path,"aphot_schema.json"), "r") as f:
    aphot_candidate_schema = json.load(f)
   
AphotCandidate = generate_candidate_class('Astrophotography', aphot_field_constructors, aphot_field_serializers, aphot_candidate_schema, BaseCandidate)            

# class AphotCandidate(BaseCandidate):
#     def __init__(self, CandidateName: str, **kwargs):
#         print(CandidateName, "in AphotConstructor")
#         self.CandidateName = CandidateName
#         # TODO: don't hardcode the module name here (but circular import?)
#         self.CandidateType = "Astrophotography"
#         self.config_schema = aphot_candidate_schema
#         self.config_constructors = aphot_field_constructors
#         self.config_serializers = aphot_field_serializers
        # TODO: this line is a problem if i want construction of these fields to be handled by the gen constructor (need to import or something):
        # for key, schema in aphot_candidate_schema.items():
        #     if key in kwargs.keys():
        #         print("aphot:",key,"set to",aphot_field_constructors[schema["valtype"]](kwargs[key], **schema))
        #         self.__dict__[key] = aphot_field_constructors[schema["valtype"]](kwargs[key], **schema)
        # super().__init__(self.CandidateName, self.CandidateType, **kwargs)