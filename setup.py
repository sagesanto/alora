
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
    package_data={},
    install_requires=['astropy','numpy','sqlalchemy','matplotlib','pandas','pytz','scipy','colorlog','tomlkit', 'astral','requests','bs4'],
    entry_points={
        'console_scripts': [
            'open = alora.dome.bin.open:main',
            'close = alora.dome.bin.close:main'
        ]
    },
)
