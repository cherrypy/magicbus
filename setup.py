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
    author_email='team@cherrypy.dev',
    description=description or name,
    long_description=long_description,
    long_description_content_type='text/x-rst',
    url='https://github.com/cherrypy/' + name,
    project_urls={
        'Tidelift: funding':
        'https://tidelift.com/subscription/pkg/pypi-magicbus'
        '?utm_source=pypi-magicbus&utm_medium=referral&utm_campaign=pypi',
        'CI: GitHub':
        'https://github.com/cherrypy/magicbus/actions?'
        'query=workflow%3A%22Test+suite%22+branch%3Amain',
    },
    packages=setuptools.find_packages(),
    include_package_data=True,
    namespace_packages=(
        name.split('.')[:-1] if nspkg_technique == 'managed'
        else []
    ),
    python_requires='>= 3.9',
    install_requires=[
    ],
    extras_require={
        'testing': [
            'pytest',
            'pytest-cov',
            'pytest-xdist',
        ],
        'docs': [
            'sphinx',
            'sphinxcontrib-towncrier',
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
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
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
