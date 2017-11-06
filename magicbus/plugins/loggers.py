"""Logging plugins for magicbus."""
from magicbus.compat import ntob, unicodestr
import datetime
import sys

from magicbus.plugins import SimplePlugin


class StreamLogger(SimplePlugin):

    default_format = '[%(timestamp)s] (Bus %(bus)s) %(message)s\n'

    def __init__(self, bus, stream, level=None, format=None, encoding='utf-8'):
        SimplePlugin.__init__(self, bus)
        self.stream = stream
        self.level = level
        self.format = format or self.default_format
        self.encoding = encoding

    def log(self, msg, level):
        if self.level is None or self.level <= level:
            params = {
                'timestamp': ntob(datetime.datetime.now().isoformat()),
                'bus': self.bus.id,
                'message': msg,
                'level': level
            }
            complete_msg = self.format % params

            if self.encoding is not None:
                if isinstance(complete_msg, unicodestr):
                    complete_msg = complete_msg.encode(self.encoding)

            self.stream.write(complete_msg)
            self.stream.flush()


class StdoutLogger(StreamLogger):

    def __init__(self, bus, level=None, format=None, encoding='utf-8'):
        StreamLogger.__init__(self, bus, sys.stdout, level, format, encoding)


class StderrLogger(StreamLogger):

    def __init__(self, bus, level=None, format=None, encoding='utf-8'):
        StreamLogger.__init__(self, bus, sys.stderr, level, format, encoding)


class FileLogger(StreamLogger):

    def __init__(self, bus, filename=None, file=None,
                 level=None, format=None, encoding='utf8'):
        self.filename = filename
        if file is None:
            if filename is None:
                raise ValueError('Either file or filename MUST be supplied.')
            file = open(filename, 'ab')

        StreamLogger.__init__(self, bus, file, level, format, encoding)
