from setuptools import setup, find_packages
from os import path

here=path.abspath( path.dirname( __file__ ) )

with open( path.join( here, 'requirements.txt' ) ) as req:
  required=req.read().splitlines()

setup(
  name="monitor",
  version="1.0.0",
  packages=find_packages(),
  entry_points={
    "console_scripts": [
      "monitor=monitor:main"
    ]
  },
  install_requires=required,

# Metadata
  author='Giancarlo Palavicini',
  author_email='kasthor@gmail.com',
  description='A simple modular monitor',
  keywords='monitor'
)
