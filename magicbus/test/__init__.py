"""Regression test suite for magicbus.

Run 'nosetests -s test/' to exercise all tests.
"""

from magicbus._compat import HTTPServer, HTTPConnection, HTTPHandler
from subprocess import Popen
import threading


def assertEqual(x, y, msg=None):
    if not x == y:
        raise AssertionError(msg or "%r != %r" % (x, y))


class Process(object):

    def __init__(self, args):
        self.args = args
        self.process = None

    def start(self):
        # Exceptions in the child will be re-raised in the parent,
        # so if yyou're expecting one, trap this call and check for it.
        self.process = Popen(self.args)

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


class WebService(object):

    def __init__(self, bus, address=('127.0.0.1', 8000), handler_class=None):
        self.bus = bus
        self.address = address
        self.handler_class = handler_class
        self.httpd = None
        self.running = False

    def subscribe(self):
        self.bus.subscribe('start', self.start)
        self.bus.subscribe('stop', self.stop)

    def start(self):
        self.httpd = WebServer(self.address, self.handler_class)
        threading.Thread(target=self.httpd.serve_forever).start()
        self.running = True
    # Make sure we start httpd after the daemonizer.
    start.priority = 75

    def stop(self):
        if self.httpd is not None:
            self.httpd.stop()
        self.running = False
    stop.priority = 25

    def do_GET(self, uri):
        conn = HTTPConnection(*self.address)
        try:
            conn.request("GET", uri)
            return conn.getresponse()
        finally:
            conn.close()


class WebHandler(HTTPHandler):

    def log_request(self, code="-", size="-"):
        if self.bus.debug:
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
        HTTPHandler.handle(self, *args, **kwargs)


class Counter(object):

    def __init__(self, bus):
        self.bus = bus
        self.running = False
        self.startcount = 0
        self.gracecount = 0
        self.threads = {}

    def subscribe(self):
        self.bus.subscribe('start', self.start)
        self.bus.subscribe('stop', self.stop)
        self.bus.subscribe('graceful', self.graceful)
        self.bus.subscribe('start_thread', self.startthread)
        self.bus.subscribe('stop_thread', self.stopthread)

    def start(self):
        self.running = True
        self.startcount += 1

    def stop(self):
        self.running = False

    def graceful(self):
        self.gracecount += 1

    def startthread(self, thread_id):
        self.threads[thread_id] = None

    def stopthread(self, thread_id):
        del self.threads[thread_id]

