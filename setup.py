#!/usr/bin/env python

import os, sys

from distutils.core import setup


def find_packages():
    # implement a simple find_packages so we don't have to depend on
    # setuptools
    packages = []
    for directory, subdirectories, files in os.walk("corotwine"):
        if '__init__.py' in files:
            packages.append(directory.replace(os.sep, '.'))
    return packages


setup_args = dict(
    name='Corotwine',
    version='0.1',
    license="MIT",
    description='Coroutines for Twisted',
    author='Christopher Armstrong',
    author_email='radix@twistedmatrix.com',
    url='http://launchpad.net/corotwine/',
    packages=find_packages(),
    )

if 'setuptools' in sys.modules:
    setup_args["install_requires"] = "Twisted>=8.1.0"


if __name__ == '__main__':
    setup(**setup_args)
