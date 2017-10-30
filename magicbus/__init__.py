"""A pub/sub Bus for managing states and transitions.

The 'process' subpackage defines a ProcessBus object, which is used to
connect applications, servers, and frameworks with site-wide services
such as daemonization, process reload, signal handling, drop privileges,
PID file management, logging for all of these, and many more.

The 'plugins' subpackage defines a few abstract and concrete services for
use with a Bus. Some use custom channels; see the documentation for each class.
"""

from magicbus.base import ChannelFailures

try:
    from magicbus.win32 import Win32Bus as Bus, Win32ProcessBus as ProcessBus
except ImportError:
    from magicbus.base import Bus
    from magicbus.process import ProcessBus
bus = ProcessBus()

__all__ = ['ChannelFailures', 'Bus', 'ProcessBus', 'bus']
