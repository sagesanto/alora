from abc import abstractmethod, ABC
from typing import Any
from astropy.units import Quantity
import astropy.units as u
from astropy.coordinates import SkyCoord, Angle
from astropy.io import fits

import numpy as np
import json
import time

from alora.astroutils.observing_utils import J2000_to_apparent
from alora.config import config

class Arg:
    def __init__(self,name,type,required,description,default=None):
        self.name = name
        self.type = type
        self.required = required
        self.description = description
        self.default = default
        if required and default is not None:
            raise ValueError("Cannot have a required argument with a default value.")
    
    @property
    def template(self):
        return self.type

    # read in the value from the request and convert it to the correct type
    def __call__(self, v:Any) -> Any:
        return v

    # serialize the value for json
    def serialize(self, value):
        return value

    def as_dict(self):
        d = {"type":self.type,"required":self.required,"description":self.description,"template":self.template}
        if self.default is not None:
            d["default"] = self.serialize(self.default)
        return d

    def __str__(self) -> str:
        return str({self.name:self.as_dict()})

    def __repr__(self) -> str:
        return self.name

class QArg(Arg):
    # a quantity argument
    @property
    def template(self):
        return {self.name:"float","unit":"str"}
    
    def __call__(self, filled:dict) -> Any:
        return Quantity(filled[self.name],unit=filled["unit"]).to(self.type)
    
    def serialize(self, value):
        return {self.name:value.value,"unit":value.unit._long_names[0]}
    

class Event(ABC):
    name = None
    allowed_job_states = None
    allowed_dome_states = None
    args_template = []

    def __init__(self,client, priority, args:dict):
        self.client = client
        self.priority = priority
        self.args = args
        
        for arg in self.required_args:
            if arg.name not in args:
                raise ValueError(f"Missing required argument: {arg}")
        for arg in args:
            if arg not in self.argnames:
                raise ValueError(f"Unexpected argument: {arg}")
        for arg in self.default_args:
            if arg.name not in args:
                args[arg.name] = arg.serialize(arg.default)
        
        argmap = {arg.name:arg for arg in self.args_template}
        self.args = {k:argmap[k](v) for k,v in self.args.items()}

    def validate_state(self,observatory):
        if self.allowed_job_states is not None and observatory.job_state not in self.allowed_job_states:
            raise ValueError(f"Cannot execute {self.name} event when observatory is in state {observatory.job_state}. Allowed states: {self.allowed_job_states}")
        if self.allowed_dome_states is not None and observatory.dome_state not in self.allowed_dome_states:
            raise ValueError(f"Cannot execute {self.name} event when dome is in state {observatory.dome_state}. Allowed states: {self.allowed_dome_states}")

    @property
    def required_args(self):
        return [arg for arg in self.args_template if arg.required]

    @property
    def default_args(self):
        return [arg for arg in self.args_template if arg.default is not None]

    @property
    def argnames(self):
        return [arg.name for arg in self.args_template]

    def execute(self,observatory):
        self.validate_state(observatory)
        self._execute(observatory)

    @classmethod
    def as_dict(cls):
        return {cls.name:{"allowed_job_states":cls.allowed_job_states,"allowed_dome_states":cls.allowed_dome_states,"args_template":{arg.name:arg.as_dict() for arg in cls.args_template}}}

    @abstractmethod
    def _execute(self,observatory):
        pass

# --------- UTILITY EVENTS ------------
class Wait(Event):
    # DANGER
    # TESTING ONLY
    # NOTE: this event is dangerous because it blocks the watchdog from shutting down the observatory. it should only be used for testing.
    name = "Wait"
    allowed_job_states = ["busy","free"]
    allowed_dome_states = None
    args_template = [Arg("duration","seconds",True,"The duration to wait.")]

    def _execute(self,observatory):
        time.sleep(self.args["duration"])

# --------- STATE CHANGES -----------
class Shutdown(Event):
    name = "Shutdown"
    allowed_job_states = ["busy","free"]
    allowed_dome_states = ["closed"]
    args_template = []

    def _execute(self,observatory):
        observatory.job_state = "shutdown"

class Reactivate(Event):
    name = "Reactivate"
    allowed_job_states = ["shutdown"]
    allowed_dome_states = None
    args_template = []

    def _execute(self,observatory):
        observatory.job_state = "free"

class Reserve(Event):
    name = "Reserve"
    allowed_job_states = ["free"]
    allowed_dome_states = None
    args_template = []

    def _execute(self,observatory):
        observatory.job_state = "busy"

class Free(Event):
    name = "Free"
    allowed_job_states = ["busy"]
    allowed_dome_states = None
    args_template = []

    def _execute(self,observatory):
        observatory.job_state = "free"

# --------- DOME/OBS EVENTS ------------

class OpenSequence(Event):
    name  = "OpenSequence"
    allowed_job_states = ["busy","free"]
    allowed_dome_states = ["closed"]
    args_template = [Arg("do_home","bool",False,"Whether to home the telescope after opening the dome.",default=False)]
      
    def _execute(self,observatory):
        observatory.open(self.args["do_home"])
    
class CloseSequence(Event):
    name = "CloseSequence"
    allowed_job_states = ["busy","free"]
    allowed_dome_states = ["open"]
    args_template = []

    def _execute(self,observatory):
        observatory.close()

class ForceOpenSequence(Event):
    name = "ForceOpenSequence"
    allowed_job_states = None
    allowed_dome_states = None
    args_template = [Arg("do_home","bool",False,"Whether to home the telescope after opening the dome.")]
    
    def _execute(self,observatory):
        observatory.open(self.args["do_home"])

class ForceCloseSequence(Event):
    name = "ForceCloseSequence"
    allowed_job_states = None
    allowed_dome_states = None
    args_template = []

    def _execute(self,observatory):
        observatory.close()

# --------- TELESCOPE EVENTS ------------
class Home(Event):
    name = "Home"
    allowed_job_states = ["busy","free"]
    allowed_dome_states = ["open"]
    args_template = []

    def _execute(self,observatory):
        observatory.telescope.home()

class Park(Event):
    name = "Park"
    allowed_job_states = ["busy","free"]
    allowed_dome_states = ["open"]
    args_template = []
 
    def _execute(self,observatory):
        observatory.telescope.park()

class Slew(Event):
    name = "Slew"
    allowed_job_states = ["busy","free"]
    allowed_dome_states = ["open"]
    args_template = [QArg("ra","deg",True,"The right ascension to slew to."),
                QArg("dec","deg",True,"The declination to slew to."),
                Arg("epoch", "str", False, "The epoch of the coordinates. Valid vals: 'J2000', 'apparent'", default="J2000"),
                Arg("closed_loop","bool",False,"Whether to perform a closed-loop slew.",default=True),
                QArg("closed_exptime","second",False,"The exposure time for the closed-loop slew. Only used if closed_loop is True.",default=2*u.second)]
    
    def _execute(self,observatory):
        observatory.slew(SkyCoord(ra=self.args["ra"],dec=self.args["dec"]),closed_loop=self.args["closed_loop"],closed_exptime=self.args["closed_exptime"],epoch=self.args["epoch"])
