#!/usr/bin/env python

# Project skeleton maintained at https://github.com/jaraco/skeleton

import io

import setuptools

with io.open('README.rst', encoding='utf-8') as readme:
    long_description = readme.read()

name = 'MagicBus'
description = 'A pub/sub state machine'
nspkg_technique = 'native'
"""
Does this package use "native" namespace packages or
pkg_resources "managed" namespace packages?
"""

params = dict(
    name=name,
    use_scm_version=True,
    author='CherryPy Team',
    author_email='team@cherrypy.org',
    description=description or name,
    long_description=long_description,
    url='https://github.com/cherrypy/' + name,
    packages=setuptools.find_packages(),
    include_package_data=True,
    namespace_packages=(
        name.split('.')[:-1] if nspkg_technique == 'managed'
        else []
    ),
    python_requires='>=2.7',
    install_requires=[
    ],
    extras_require={
        'testing': [
            'nose',
            'collective.checkdocs',
        ],
        'docs': [
            'sphinx',
            'jaraco.packaging>=3.2',
            'rst.linker>=1.9',
        ],
    },
    setup_requires=[
        'setuptools_scm>=1.15.0',
    ],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: HTTP Servers',
        'Topic :: Software Development :: Libraries :: Application Frameworks',
    ],
    entry_points={
    },
)
if __name__ == '__main__':
    setuptools.setup(**params)
