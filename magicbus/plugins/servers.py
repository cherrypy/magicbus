"""
Multiple servers/ports
======================

If you need to start more than one HTTP server (to serve on multiple ports, or
protocols, etc.), you can manually register each one and then start them all
with bus.transition("RUN")::

    s1 = ServerPlugin(bus, MyWSGIServer(host='0.0.0.0', port=80))
    s2 = ServerPlugin(bus, another.HTTPServer(host='127.0.0.1', SSL=True))
    s1.subscribe()
    s2.subscribe()
    bus.transition("RUN")

.. index:: SCGI

FastCGI/SCGI
============

There are also Flup\ **F**\ CGIServer and Flup\ **S**\ CGIServer classes in
:mod:`magicbus.plugins.servers`. To start an fcgi server, for example,
wrap an instance of it in a ServerPlugin::

    addr = ('0.0.0.0', 4000)
    f = servers.FlupFCGIServer(application=mywsgiapp, bindAddress=addr)
    s = servers.ServerPlugin(bus, httpserver=f, bind_addr=addr)
    s.subscribe()

Note that you need to download and install `flup <http://trac.saddi.com/flup>`_
yourself.

.. _fastcgi:
.. index:: FastCGI

FastCGI
-------

A very simple setup lets your server run with FastCGI.
You just need the flup library,
plus a running Apache server (with ``mod_fastcgi``) or lighttpd server.

Apache
^^^^^^

At the top level in httpd.conf::

    FastCgiIpcDir /tmp
    FastCgiServer /path/to/myapp.fcgi -idle-timeout 120 -processes 4

And inside the relevant VirtualHost section::

    # FastCGI config
    AddHandler fastcgi-script .fcgi
    ScriptAliasMatch (.*$) /path/to/myapp.fcgi$1

Lighttpd
^^^^^^^^

For `Lighttpd <http://www.lighttpd.net/>`_ you can follow these
instructions. Within ``lighttpd.conf`` make sure ``mod_fastcgi`` is
active within ``server.modules``. Then, within your ``$HTTP["host"]``
directive, configure your fastcgi script like the following::

    $HTTP["url"] =~ "" {
      fastcgi.server = (
        "/" => (
          "script.fcgi" => (
            "bin-path" => "/path/to/your/script.fcgi",
            "socket"          => "/tmp/script.sock",
            "check-local"     => "disable",
            "disable-time"    => 1,
            "min-procs"       => 1,
            "max-procs"       => 1, # adjust as needed
          ),
        ),
      )
    } # end of $HTTP["url"] =~ "^/"

Please see `Lighttpd FastCGI Docs
<http://redmine.lighttpd.net/wiki/lighttpd/Docs:ModFastCGI>`_ for an
explanation of the possible configuration options.
"""

import socket
import sys
import threading
import time
import warnings


class ServerPlugin:
    """Bus plugin for an HTTP server.

    You don't have to use this plugin; you can make your own that listens on
    the appropriate bus channels. This one is designed to:

        * wrap HTTP servers whose accept loop blocks by running it in a
          separate thread; any exceptions in it exit the bus
        * wait until the server is truly ready to receive requests before
          returning from the bus START listener
        * wait until the server has finished processing requestss before
          returning from the bus STOP listener
        * log server start/stop via the bus

    The httpserver argument MUST possess 'start' and 'stop' methods,
    and a 'ready' boolean attribute which is True when the HTTP server
    is ready to receive requests on its socket.

    If you need to start more than one HTTP server (to serve on multiple
    ports, or protocols, etc.), you can manually register each one and then
    start them all with bus.transition("RUN")::

        s1 = ServerPlugin(bus, MyWSGIServer(host='0.0.0.0', port=80))
        s2 = ServerPlugin(bus, another.HTTPServer(host='127.0.0.1', SSL=True))
        s1.subscribe()
        s2.subscribe()
        bus.transition("RUN")
    """

    def __init__(self, bus, httpserver=None, bind_addr=None):
        self.bus = bus
        self.httpserver = httpserver
        self.bind_addr = bind_addr
        self.interrupt = None
        self.running = False

    def subscribe(self):
        self.bus.subscribe('START', self.START)
        self.bus.subscribe('STOP', self.STOP)

    def unsubscribe(self):
        self.bus.unsubscribe('START', self.START)
        self.bus.unsubscribe('STOP', self.STOP)

    @property
    def interface(self):
        if self.bind_addr is None:
            return 'unknown interface (dynamic?)'
        elif isinstance(self.bind_addr, tuple):
            host, port = self.bind_addr
            return '%s:%s' % (host, port)
        else:
            return 'socket file: %s' % self.bind_addr

    def START(self):
        """Start the HTTP server."""
        if self.running:
            self.bus.log('Already serving on %s' % self.interface)
            return

        self.interrupt = None
        if not self.httpserver:
            raise ValueError('No HTTP server has been created.')

        # Start the httpserver in a new thread.
        if isinstance(self.bind_addr, tuple):
            wait_for_free_port(*self.bind_addr)

        t = threading.Thread(target=self._start_http_thread)
        t.setName('HTTPServer ' + t.getName())
        self.bus.log('Starting on %s' % self.interface)
        t.start()

        self.wait()
        self.running = True
        self.bus.log('Serving on %s' % self.interface)
    START.priority = 75

    def _start_http_thread(self):
        """HTTP servers MUST be running in new threads, so that the
        main thread persists to receive KeyboardInterrupt's. If an
        exception is raised in the httpserver's thread then it's
        trapped here, and the bus (and therefore our httpserver)
        are shut down.
        """
        try:
            self.httpserver.start()
        except KeyboardInterrupt:
            self.bus.log('<Ctrl-C> hit: shutting down HTTP server')
            self.interrupt = sys.exc_info()[1]
            self.bus.transition('EXITED')
        except SystemExit:
            self.bus.log('SystemExit raised: shutting down HTTP server')
            self.interrupt = sys.exc_info()[1]
            self.bus.transition('EXITED')
            raise
        except:
            self.interrupt = sys.exc_info()[1]
            self.bus.log('Error in HTTP server: shutting down',
                         traceback=True, level=40)
            self.bus.transition('EXITED')
            raise

    def wait(self):
        """Wait until the HTTP server is ready to receive requests."""
        while not getattr(self.httpserver, 'ready', False):
            if self.interrupt:
                raise self.interrupt
            time.sleep(.1)

        # Wait for port to be occupied
        if isinstance(self.bind_addr, tuple):
            host, port = self.bind_addr
            self.bus.log('Waiting for %s' % self.interface)
            wait_for_occupied_port(host, port)

    def STOP(self):
        """Stop the HTTP server."""
        if self.running:
            # stop() MUST block until the server is *truly* stopped.
            self.httpserver.stop()
            # Wait for the socket to be truly freed.
            if isinstance(self.bind_addr, tuple):
                wait_for_free_port(*self.bind_addr)
            self.running = False
            self.bus.log('HTTP Server %s shut down' % self.httpserver)
        else:
            self.bus.log('HTTP Server %s already shut down' % self.httpserver)
    STOP.priority = 25


# ------- Wrappers for various HTTP servers for use with ServerPlugin ------- #
# These are not plugins, so they don't use the bus states as method names.

class FlupCGIServer:
    """Adapter for a flup.server.cgi.WSGIServer."""

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.ready = False

    def start(self):
        """Start the CGI server."""
        # We have to instantiate the server class here because its __init__
        # starts a threadpool. If we do it too early, daemonize won't work.
        from flup.server.cgi import WSGIServer

        self.cgiserver = WSGIServer(*self.args, **self.kwargs)
        self.ready = True
        self.cgiserver.run()

    def stop(self):
        """Stop the HTTP server."""
        self.ready = False


class FlupFCGIServer:
    """Adapter for a flup.server.fcgi.WSGIServer."""

    def __init__(self, *args, **kwargs):
        if kwargs.get('bindAddress', None) is None:
            if not hasattr(socket, 'fromfd'):
                raise ValueError(
                    'Dynamic FCGI server not available on this platform. '
                    'You must use a static or external one by providing a '
                    'legal bindAddress.')
        self.args = args
        self.kwargs = kwargs
        self.ready = False

    def start(self):
        """Start the FCGI server."""
        # We have to instantiate the server class here because its __init__
        # starts a threadpool. If we do it too early, daemonize won't work.
        from flup.server.fcgi import WSGIServer
        self.fcgiserver = WSGIServer(*self.args, **self.kwargs)
        # TODO: report this bug upstream to flup.
        # If we don't set _oldSIGs on Windows, we get:
        #   File "C:\Python24\Lib\site-packages\flup\server\threadedserver.py",
        #   line 108, in run
        #     self._restoreSignalHandlers()
        #   File "C:\Python24\Lib\site-packages\flup\server\threadedserver.py",
        #   line 156, in _restoreSignalHandlers
        #     for signum,handler in self._oldSIGs:
        #   AttributeError: 'WSGIServer' object has no attribute '_oldSIGs'
        self.fcgiserver._installSignalHandlers = lambda: None
        self.fcgiserver._oldSIGs = []
        self.ready = True
        self.fcgiserver.run()

    def stop(self):
        """Stop the HTTP server."""
        # Forcibly stop the fcgi server main event loop.
        self.fcgiserver._keepGoing = False
        # Force all worker threads to die off.
        self.fcgiserver._threadPool.maxSpare = (
            self.fcgiserver._threadPool._idleCount)
        self.ready = False


class FlupSCGIServer:
    """Adapter for a flup.server.scgi.WSGIServer."""

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.ready = False

    def start(self):
        """Start the SCGI server."""
        # We have to instantiate the server class here because its __init__
        # starts a threadpool. If we do it too early, daemonize won't work.
        from flup.server.scgi import WSGIServer
        self.scgiserver = WSGIServer(*self.args, **self.kwargs)
        # TODO: report this bug upstream to flup.
        # If we don't set _oldSIGs on Windows, we get:
        #   File "C:\Python24\Lib\site-packages\flup\server\threadedserver.py",
        #   line 108, in run
        #     self._restoreSignalHandlers()
        #   File "C:\Python24\Lib\site-packages\flup\server\threadedserver.py",
        #   line 156, in _restoreSignalHandlers
        #     for signum,handler in self._oldSIGs:
        #   AttributeError: 'WSGIServer' object has no attribute '_oldSIGs'
        self.scgiserver._installSignalHandlers = lambda: None
        self.scgiserver._oldSIGs = []
        self.ready = True
        self.scgiserver.run()

    def stop(self):
        """Stop the HTTP server."""
        self.ready = False
        # Forcibly stop the scgi server main event loop.
        self.scgiserver._keepGoing = False
        # Force all worker threads to die off.
        self.scgiserver._threadPool.maxSpare = 0


# ---------------------------- Utility functions ---------------------------- #

def client_host(server_host):
    """Return the host on which a client can connect to the given listener."""
    if server_host == '0.0.0.0':
        # 0.0.0.0 is INADDR_ANY, which should answer on localhost.
        return '127.0.0.1'
    if server_host in ('::', '::0', '::0.0.0.0'):
        # :: is IN6ADDR_ANY, which should answer on localhost.
        # ::0 and ::0.0.0.0 are non-canonical but common ways to write
        # IN6ADDR_ANY.
        return '::1'
    return server_host


def check_port(host, port, timeout=1.0):
    """Raise OSError if the given port is not free on the given host."""
    if not host:
        raise ValueError("Host values of '' or None are not allowed.")
    host = client_host(host)
    port = int(port)

    # AF_INET or AF_INET6 socket
    # Get the correct address family for our host (allows IPv6 addresses)
    try:
        info = socket.getaddrinfo(host, port, socket.AF_UNSPEC,
                                  socket.SOCK_STREAM)
    except socket.gaierror:
        if ':' in host:
            info = [
                (socket.AF_INET6, socket.SOCK_STREAM, 0, '',
                 (host, port, 0, 0))]
        else:
            info = [(socket.AF_INET, socket.SOCK_STREAM, 0, '', (host, port))]

    for res in info:
        af, socktype, proto, canonname, sa = res
        s = None
        try:
            s = socket.socket(af, socktype, proto)
            # See http://groups.google.com/group/cherrypy-users/
            #        browse_frm/thread/bbfe5eb39c904fe0
            s.settimeout(timeout)
            s.connect((host, port))
            s.close()
        except (IOError, OSError):
            if s:
                s.close()
        else:
            raise OSError(
                'Port %s is in use on %s; perhaps the previous '
                'httpserver did not shut down properly.' %
                (repr(port), repr(host))
            )


# Feel free to increase these defaults on slow systems:
free_port_timeout = 0.1
occupied_port_timeout = 0.25


def wait_for_free_port(host, port, timeout=None):
    """Wait for the specified port to become free (drop requests)."""
    if not host:
        raise ValueError("Host values of '' or None are not allowed.")
    if timeout is None:
        timeout = free_port_timeout

    for trial in range(50):
        try:
            # we are expecting a free port, so reduce the timeout
            check_port(host, port, timeout=timeout)
        except OSError:
            # Give the old server thread time to free the port.
            time.sleep(timeout)
        else:
            return

    raise OSError('Port %r not free on %r' % (port, host))


def wait_for_occupied_port(host, port, timeout=None):
    """Wait for the specified port to become active (receive requests)."""
    if not host:
        raise ValueError("Host values of '' or None are not allowed.")
    if timeout is None:
        timeout = occupied_port_timeout

    for trial in range(50):
        try:
            check_port(host, port, timeout=timeout)
        except OSError:
            return
        else:
            time.sleep(timeout)

    if host == client_host(host):
        raise OSError('Port %r not bound on %r' % (port, host))

    # On systems where a loopback interface is not available and the
    #  server is bound to all interfaces, it's difficult to determine
    #  whether the server is in fact occupying the port. In this case,
    # just issue a warning and move on. See issue #1100.
    msg = 'Unable to verify that the server is bound on %r' % port
    warnings.warn(msg)
