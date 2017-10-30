from magicbus.compat import ntob
import os
thismodule = os.path.abspath(__file__)
import sys

from magicbus import bus
from magicbus.plugins import opsys
from magicbus.test import assertEqual, Process, WebAdapter, WebService
from magicbus.test import WebHandler

# from magicbus.plugins import loggers
# loggers.StdoutLogger(bus).subscribe()

pidfile = opsys.PIDFile(bus, os.path.join(thismodule + '.pid'))


class Handler(WebHandler):

    bus = bus

    def do_GET(self):
        if self.path == '/':
            self.respond('Hello World')
        elif self.path == '/pid':
            self.respond(str(os.getpid()))
        elif self.path == '/exit':
            self.respond('ok')
            self.bus.transition('EXITED')
        else:
            self.respond(status=404)
service = WebService(handler_class=Handler)


class TestOpsys(object):

    def test_daemonize(self):
        if os.name not in ['posix']:
            return 'skipped (not on posix)'

        # Spawn the process and wait, when this returns, the original process
        # is finished.  If it daemonized properly, we should still be able
        # to access pages.
        p = Process([sys.executable, thismodule, 'daemonize'])
        p.start()
        pidfile.wait()
        try:
            # Just get the pid of the daemonization process.
            resp = service.do_GET('/pid')
            assertEqual(resp.status, 200)
            page_pid = int(resp.read())
            assertEqual(ntob(str(page_pid)),
                        open(pidfile.pidfile, 'rb').read())
        finally:
            # Shut down the spawned process
            service.do_GET('/exit')
        pidfile.join()

        # Wait until here to test the exit code because we want to ensure
        # that we wait for the daemon to finish running before we fail.
        p.process.wait()
        if p.process.returncode != 0:
            raise AssertionError(
                'Daemonized parent process returned exit code %s.' %
                p.process.returncode)


if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'daemonize':
        opsys.Daemonizer(bus).subscribe()
    pidfile.subscribe()
    WebAdapter(bus, service).subscribe()
    bus.transition('RUN')
    bus.block()
