"""Compatibility code for using magicbus with various versions of Python.

Magic Bus 3.3 is compatible with Python versions 2.7+. This module provides a
useful abstraction over the differences between Python versions, sometimes by
preferring a newer idiom, sometimes an older one, and sometimes a custom one.

In particular, Python 2 uses str and '' for byte strings, while Python 3
uses str and '' for unicode strings. We will call each of these the 'native
string' type for each version. Because of this major difference, this module
provides new 'bytestr', 'unicodestr', and 'nativestr' attributes, as well as
the function: 'ntob', which translates native strings (of type 'str') into
byte strings regardless of Python version.
"""
import sys

if sys.version_info >= (3, 0):
    py3k = True
    basestring = (bytes, str)
    unicodestr = str

    def ntob(n, encoding='ISO-8859-1'):
        """Return the given native string as a byte string in the given
        encoding."""
        # In Python 3, the native string type is unicode
        return n.encode(encoding)
else:
    # Python 2
    py3k = False
    basestring = basestring
    unicodestr = unicode

    def ntob(n, encoding='ISO-8859-1'):
        """Return the given native string as a byte string in the given
        encoding."""
        # In Python 2, the native string type is bytes. Assume it's already
        # in the given encoding, which for ISO-8859-1 is almost always what
        # was intended.
        return n

try:
    from http.server import HTTPServer, BaseHTTPRequestHandler as HTTPHandler
except ImportError:
    from BaseHTTPServer import HTTPServer
    from BaseHTTPServer import BaseHTTPRequestHandler as HTTPHandler

try:
    from http.client import HTTPConnection
except ImportError:
    from httplib import HTTPConnection


import threading


try:
    from _thread import get_ident as get_thread_ident
except ImportError:
    from thread import get_ident as get_thread_ident


if sys.version_info >= (3, 3):
    TimerClass = threading.Timer
else:
    TimerClass = threading._Timer
