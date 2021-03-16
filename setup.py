#!/usr/bin/env python

from setuptools import setup

setup(name='tap-recurly',
      version='1.0.0',
      description='Singer.io tap for extracting data from the Recurly API',
      author='Stitch',
      url='http://github.com/singer-io/tap-recurly',
      classifiers=['Programming Language :: Python :: 3 :: Only'],
      py_modules=['tap_recurly'],
      install_requires=[
          'singer-python==5.1.5',
          'requests==2.20.0',
          'backoff==1.3.2'
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
