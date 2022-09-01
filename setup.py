#!/usr/bin/env python

from distutils.core import setup

setup(name='WaitForchecks',
      version='1.0',
      description='Wait for checks to pass or fail on a Github PR or commit',
      author='Porter Westling',
      author_email='pwestling@gmail.com',
      packages=['github', 'curses'],
     )
