"""Regression test suite for magicbus.

Run 'tox' to exercise all tests.
"""

from magicbus.compat import HTTPServer, HTTPConnection, HTTPHandler
import os
from subprocess import Popen
import threading
import time

from magicbus.plugins import SimplePlugin


def assertEqual(x, y, msg=None):
    if not x == y:
        raise AssertionError(msg or '%r != %r' % (x, y))


def assertNotEqual(x, y, msg=None):
    if x == y:
        raise AssertionError(msg or '%r == %r' % (x, y))


class Process(object):

    def __init__(self, args):
        self.args = args
        self.process = None

    def start(self):
        # Exceptions in the child will be re-raised in the parent,
        # so if you're expecting one, trap this call and check for it.
        cwd = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
        env = os.environ.copy()
        env['PYTHONPATH'] = cwd
        self.process = Popen(self.args, env=env)

    def stop(self):
        if self.process is not None:
            self.process.kill()

    def join(self):
        return self.process.wait()


class WebServer(HTTPServer):

    def stop(self):
        """Stops the serve_forever loop without waiting."""
        # Sigh. Really, standard library, really? Double underscores?
        self._BaseServer__shutdown_request = True

    def handle_error(self, request, client_address):
        # Simulate unsafe servers that don't trap errors well
        raise


class WebService(object):

    def __init__(self, address=('127.0.0.1', 8000), handler_class=None):
        self.address = address
        self.handler_class = handler_class
        self.httpd = None
        self.ready = False

    def start(self):
        self.httpd = WebServer(self.address, self.handler_class)
        self.ready = True
        self.httpd.serve_forever()

    def stop(self):
        if self.httpd is not None:
            self.httpd.stop()
        self.httpd = None
        self.ready = False

    def do_GET(self, uri):
        conn = HTTPConnection(*self.address)
        try:
            conn.request('GET', uri)
            return conn.getresponse()
        finally:
            conn.close()


class WebAdapter(SimplePlugin):

    def __init__(self, bus, service):
        self.bus = bus
        self.service = service

    def START(self):
        threading.Thread(target=self.service.start).start()
        self.wait()
    # Make sure we start httpd after the daemonizer and pidfile.
    START.priority = 75

    def STOP(self):
        self.service.stop()
    STOP.priority = 25

    def wait(self):
        """Wait until the HTTP server is ready to receive requests."""
        while not getattr(self.service, 'ready', False):
            time.sleep(.1)


class WebHandler(HTTPHandler):

    def log_request(self, code='-', size='-'):
        HTTPHandler.log_request(self, code, size)

    def respond(self, body=None, status=200, headers=None):
        if headers is None:
            headers = []
        if body is not None:
            if isinstance(body, str):
                body = body.encode('utf-8')
            if 'Content-Length' not in (k for k, v in headers):
                headers.append(('Content-Length', str(len(body))))
        self.send_response(status)
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        if body is not None:
            self.wfile.write(body)

    def handle(self, *args, **kwargs):
        self.bus.publish('acquire_thread')
        HTTPHandler.handle(self)
