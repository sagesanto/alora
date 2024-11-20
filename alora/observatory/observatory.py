import os
import dotenv
from . import Telescope, Dome

class Observatory:
    def __init__(self):
        self.telescope = None
        self.dome = None
    
    def connect(self):
        self.telescope = Telescope()
        dotenv.load_dotenv()
        self.dome = Dome(os.getenv("DOME_ADDR"),os.getenv("DOME_USERNAME"),os.getenv("DOME_PASSWORD"))