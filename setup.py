#!/usr/bin/env python

from distutils.core import setup

setup(name='WaitForChecks',
      version='1.0',
      description='Wait for checks to pass or fail on a Github PR or commit',
      author='Porter Westling',
      author_email='pwestling@gmail.com',
      packages=["wait_for_checks"],
      entry_points={
        'console_scripts': ['wait_for_checks=wait_for_checks.wait_for_checks:main'],
      },
     )
