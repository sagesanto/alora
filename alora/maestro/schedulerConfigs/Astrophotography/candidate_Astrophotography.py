import sys, os, json
from os.path import abspath, dirname, join, pardir

MAESTRO_PATH = abspath(join(dirname(__file__),pardir,pardir))
module_path = abspath(dirname(__file__))

sys.path.append(MAESTRO_PATH)
import scheduleLib.genUtils
from scheduleLib.candidateDatabase import BaseCandidate, construct_quantity

aphot_field_constructors = {"quantity":construct_quantity}
aphot_field_deconstructors = {}

with open(join(module_path,"aphot_schema.json"), "r") as f:
    aphot_candidate_schema = json.load(f)

class CandidateClassFactory:
    def __init__(self,config_name,config_constructors,config_serializers):
        class AphotCandidate(BaseCandidate):
            def __init__(self, CandidateName: str, **kwargs):
                self.CandidateName = CandidateName
                # TODO: don't hardcode the module name here (but circular import?)
                self.CandidateType = config_name
                # TODO: this line is a problem if i want construction of these fields to be handled by the gen constructor (need to import or something):
                for key, schema in aphot_candidate_schema.items():
                    if key in kwargs.keys():
                        self.__dict__[key] = config_constructors[schema["valtype"]](kwargs[key], **schema)
                super().__init__(self.CandidateName, self.CandidateType, **kwargs)
            
            

class AphotCandidate(BaseCandidate):
    def __init__(self, CandidateName: str, **kwargs):
        self.CandidateName = CandidateName
        # TODO: don't hardcode the module name here (but circular import?)
        self.CandidateType = "Astrophotography"
        # TODO: this line is a problem if i want construction of these fields to be handled by the gen constructor (need to import or something):
        for key, schema in aphot_candidate_schema.items():
            if key in kwargs.keys():
                self.__dict__[key] = aphot_field_constructors[schema["valtype"]](kwargs[key], **schema)
        super().__init__(self.CandidateName, self.CandidateType, **kwargs)