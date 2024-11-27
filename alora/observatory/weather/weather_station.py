import requests
from abc import abstractmethod, abstractproperty, ABC

class WeatherStation(ABC):
    def __init__(self) -> None:
        super().__init__()

    @abstractproperty
    def connected(self) -> bool:
        pass

    @abstractproperty
    def weather_is_safe(self) -> bool:
        pass
