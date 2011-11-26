"""An implementation of the Web Site Process Bus.

A Web Site Process Bus object is used to connect applications, servers,
and frameworks with site-wide services such as daemonization, process
reload, signal handling, drop privileges, PID file management, logging
for all of these, and many more.

The 'plugins' subpackage defines a few abstract and concrete services for
use with the bus. Some use tool-specific channels; see the documentation
for each class.
"""

try:
    from magicbus import win32
    bus = win32.Win32Bus()
    bus.console_control_handler = win32.ConsoleCtrlHandler(bus)
    del win32
except ImportError:
    from magicbus.wspbus import Bus
    bus = Bus()
