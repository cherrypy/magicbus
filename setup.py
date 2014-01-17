"""Installs magicbus using distutils

Run:
    python setup.py install

to install this package.
"""

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

from distutils.command.install import INSTALL_SCHEMES
import sys

###############################################################################
# arguments for the setup command
###############################################################################
name = "MagicBus"
version = "3.3.0alpha"
desc = "An implementation of the Web Site Process Bus"
long_desc = ("The Process Bus is a publish/subscribe architecture that"
             " loosely connects components with services.")
classifiers = [
    "Development Status :: 3 - Alpha",
    "Environment :: Web Environment",
    "Intended Audience :: Developers",
    "License :: Freely Distributable",
    "Operating System :: OS Independent",
    "Programming Language :: Python",
    "Programming Language :: Python :: 2",
    "Programming Language :: Python :: 3",
    "Topic :: Internet :: WWW/HTTP",
    "Topic :: Internet :: WWW/HTTP :: HTTP Servers",
    "Topic :: Software Development :: Libraries :: Application Frameworks",
]
author = "CherryPy Team"
author_email = "team@cherrypy.org"
url = "http://www.cherrypy.org"
cp_license = "BSD"
packages = [
    "magicbus", "magicbus.plugins",
    "magicbus.test",
]
download_url = "http://download.cherrypy.org/magicbus/3.3.0alpha/"
data_files = [
    ('magicbus', ['magicbus/LICENSE.txt']),
    ('magicbus/plugins', []),
    ('magicbus/test', []),
]

if sys.version_info >= (3, 0):
    required_python_version = '3.3'
else:
    required_python_version = '2.7'

###############################################################################
# end arguments for setup
###############################################################################

# wininst may install data_files in Python/x.y instead of the magicbus package.
# Django's solution is at http://code.djangoproject.com/changeset/8313
# See also
# http://mail.python.org/pipermail/distutils-sig/2004-August/004134.html
if 'bdist_wininst' in sys.argv or '--format=wininst' in sys.argv:
    data_files = [(r'\PURELIB\%s' % path, files) for path, files in data_files]


def main():
    if sys.version < required_python_version:
        s = "I'm sorry, but %s %s requires Python %s or later."
        print(s % (name, version, required_python_version))
        sys.exit(1)
    # set default location for "data_files" to
    # platform specific "site-packages" location
    for scheme in list(INSTALL_SCHEMES.values()):
        scheme['data'] = scheme['purelib']

    setup(
        name=name,
        version=version,
        description=desc,
        long_description=long_desc,
        classifiers=classifiers,
        author=author,
        author_email=author_email,
        url=url,
        license=cp_license,
        packages=packages,
        download_url=download_url,
        data_files=data_files,
    )


if __name__ == "__main__":
    main()
