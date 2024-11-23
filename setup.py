
import os
import site
from setuptools import setup, find_packages

''' Run this file using

sudo python setup.py develop

To install the python telescope control package. Using the 'develop'
option (rather than 'install') allows you to make changes to the code
without having to rebuild the package
'''

# do setup
setup(
    name="alora",
    version="0.0.1",
    description='Software for Alora Observatory',
    author='Sage Santomenna',
    author_email='sage.santomenna@gmail.com',
    packages=find_packages(include=['alora', 'alora.*']),
    package_data={"alora":["observatory/config/config.toml","observatory/config/logging.json"]},
    install_requires=['astropy','numpy','sqlalchemy','matplotlib','pandas','pytz','scipy','colorlog','tomlkit', 'astral','requests','bs4','python-dotenv','astroplan', 'PyQt6','tomli', 'seaborn', 'pywin32', 'flask'],
    entry_points={
        'console_scripts': [
            'emergency_open = alora.observatory.dome.bin.emergency_open:main',
            'emergency_close = alora.observatory.dome.bin.emergency_close:main',
            'maestro = alora.maestro.app:main',
            'open = alora.observatory.bin.open:main',
            'close = alora.observatory.bin.close:main',
            'slew_to = alora.observatory.bin.slew_to:main',
            'take_images = alora.observatory.bin.take_images:main'
        ]
    },
)
