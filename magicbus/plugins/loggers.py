"""Logging plugins for magicbus."""

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



