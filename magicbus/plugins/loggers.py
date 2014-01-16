"""Logging plugins for magicbus."""
from magicbus.compat import ntob
import datetime
import sys

from magicbus.plugins import SimplePlugin


class StdoutLogger(SimplePlugin):

    def __init__(self, bus, level=None):
        SimplePlugin.__init__(self, bus)
        self.level = level

    def log(self, msg, level):
        if self.level is None or self.level <= level:
            sys.stdout.write(msg + '\n')
            sys.stdout.flush()


class FileLogger(SimplePlugin):

    def __init__(self, bus, filename=None, file=None, encoding='utf8',
                 level=None):
        SimplePlugin.__init__(self, bus)
        self.filename = filename
        self.file = file
        self.encoding = encoding
        self.level = level

    def start(self):
        if self.filename is not None:
            self.file = open(self.filename, 'wb')
    start.priority = 0

    def log(self, msg, level):
        if (
            (self.level is None or self.level <= level) and
            self.file is not None
        ):
            if isinstance(msg, str):
                msg = msg.encode(self.encoding)
            self.file.write(
                b'[' +
                ntob(datetime.datetime.now().isoformat()) +
                b'] ' +
                msg +
                b'\n'
            )
            self.file.flush()

    def stop(self):
        if self.filename is not None:
            self.file.close()
            self.file = None
    stop.priority = 100
