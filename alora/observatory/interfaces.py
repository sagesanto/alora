from abc import ABC, abstractmethod, abstractproperty
from typing import Union, Callable, Tuple
from astropy.coordinates import SkyCoord
from alora.observatory.config import default_binning

class Telescope(ABC):
    def __init__(self,write_out:Callable[[str],None]=print) -> None:
        self.write_out = write_out
    
    @property
    @abstractmethod
    def pos(self) -> SkyCoord:
        pass

    @property
    @abstractmethod
    def connected(self) -> bool:
        pass

    @abstractmethod
    def home(self):
        pass

    @property
    @abstractmethod
    def parked(self) -> bool:
        pass

    @abstractmethod
    def park(self) -> Tuple[bool,Union[str,int]]:
        pass

    @abstractmethod
    def slew(self, coord:SkyCoord):
        pass

    @abstractmethod
    def track_sidereal(self):
        pass

    @abstractmethod
    def stop_tracking(self):
        pass


class Camera(ABC):
    def __init__(self,write_out:Callable[[str],None]=print) -> None:
        self.write_out = write_out

    @property
    @abstractmethod
    def connected(self) -> bool:
        pass

    @abstractmethod
    def take_dataset(self, nframes:int, exptime:float, filter:str, outdir:str, exp_delay:float=0, name_prefix:str='im', binning:int=default_binning) -> Tuple[Union[bool,None],Union[str,int]]:
        pass

class Dome(ABC):
    def __init__(self,write_out:Callable[[str],None]=print) -> None:
        self.write_out = write_out
    
    @abstractmethod
    def _open(self):
        pass

    @abstractmethod
    def _close(self):
        pass

class PlateSolve(ABC):
    def __init__(self,write_out:Callable[[str],None]=print) -> None:
        self.write_out = write_out

    @abstractmethod
    def solve(self, impath, **kwargs):
        pass

    # @abstractmethod
    # def solve_data(self, data, **kwargs):
        # ffile = temp