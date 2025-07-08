#!/usr/bin/env python

from setuptools import setup

setup(name='tap-recurly',
      version='1.0.1',
      description='Singer.io tap for extracting data from the Recurly API',
      author='Stitch',
      url='http://github.com/singer-io/tap-recurly',
      classifiers=['Programming Language :: Python :: 3 :: Only'],
      py_modules=['tap_recurly'],
      install_requires=[
          'singer-python==5.13.2',
          'requests==2.32.4',
          'backoff==1.10.0'
      ],
      extras_require={
        'dev': [
            'ipdb==0.13.7',
            'pylint==2.7.2',
        ]
      },
      entry_points='''
          [console_scripts]
          tap-recurly=tap_recurly:main
      ''',
      packages=['tap_recurly'],
      package_data = {
          "schemas": ["tap_recurly/schemas/*.json"]
      },
      include_package_data=True,
)
