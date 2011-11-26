from magicbus._compat import BadStatusLine, ntob
import os
import sys
import threading
import time

from magicbus import bus
thisdir = os.path.join(os.getcwd(), os.path.dirname(__file__))


class WebService:

    def __init__(self, bus):
        self.bus = bus
        self.running = False

    def subscribe(self):
        self.bus.subscribe('start', self.start)
        self.bus.subscribe('stop', self.stop)

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def __call__(self, environ, start_response):
        self.bus.publish('acquire_thread')
        try:
            pi = environ["PATH_INFO"]
            if pi == '/':
                start_response('200 OK', [('Content-type', 'text/plain')])
                return ["Hello world!"]
            raise ValueError("Unknown URI")
        finally:
            self.bus.publish('release_thread')


class Dependency:

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


        def ctrlc(self):
            raise KeyboardInterrupt()
        ctrlc.exposed = True

        def graceful(self):
            bus.graceful()
            return "app was (gracefully) restarted succesfully"
        graceful.exposed = True


class StateTests(object):

    def test_normal_flow(self):
        bus.clear()

        service = WebService(bus)

        # Our db_connection should not be running
        db_connection = Dependency(bus)
        db_connection.subscribe()
        self.assertEqual(db_connection.running, False)
        self.assertEqual(db_connection.startcount, 1)
        self.assertEqual(len(db_connection.threads), 0)

        # Test server start
        bus.start()
        self.assertEqual(bus.state, bus.states.STARTED)

        self.assertEqual(service.running, True)

        # The db_connection should be running now
        self.assertEqual(db_connection.running, True)
        self.assertEqual(db_connection.startcount, 2)
        self.assertEqual(len(db_connection.threads), 0)

        response = service("/")
        self.assertEqual(response, "Hello World")
        self.assertEqual(len(db_connection.threads), 1)

        # Test bus stop. This will also stop the HTTP server.
        bus.stop()
        self.assertEqual(bus.state, bus.states.STOPPED)

        # Verify that our custom stop function was called
        self.assertEqual(db_connection.running, False)
        self.assertEqual(len(db_connection.threads), 0)

        # Block the main thread now and verify that exit() works.
        def exittest():
            self.getPage("/")
            self.assertBody("Hello World")
            bus.exit()
        cherrypy.server.start()
        bus.start_with_callback(exittest)
        bus.block()
        self.assertEqual(bus.state, bus.states.EXITING)

    def test_1_Restart(self):
        cherrypy.server.start()
        bus.start()

        # The db_connection should be running now
        self.assertEqual(db_connection.running, True)
        grace = db_connection.gracecount

        self.getPage("/")
        self.assertBody("Hello World")
        self.assertEqual(len(db_connection.threads), 1)

        # Test server restart from this thread
        bus.graceful()
        self.assertEqual(bus.state, bus.states.STARTED)
        self.getPage("/")
        self.assertBody("Hello World")
        self.assertEqual(db_connection.running, True)
        self.assertEqual(db_connection.gracecount, grace + 1)
        self.assertEqual(len(db_connection.threads), 1)

        # Test server restart from inside a page handler
        self.getPage("/graceful")
        self.assertEqual(bus.state, bus.states.STARTED)
        self.assertBody("app was (gracefully) restarted succesfully")
        self.assertEqual(db_connection.running, True)
        self.assertEqual(db_connection.gracecount, grace + 2)
        # Since we are requesting synchronously, is only one thread used?
        # Note that the "/graceful" request has been flushed.
        self.assertEqual(len(db_connection.threads), 0)

        bus.stop()
        self.assertEqual(bus.state, bus.states.STOPPED)
        self.assertEqual(db_connection.running, False)
        self.assertEqual(len(db_connection.threads), 0)

    def test_2_KeyboardInterrupt(self):
        # Raise a keyboard interrupt in the HTTP server's main thread.
        # We must start the server in this, the main thread
        bus.start()
        cherrypy.server.start()

        self.persistent = True
        try:
            # Make the first request and assert there's no "Connection: close".
            self.getPage("/")
            self.assertStatus('200 OK')
            self.assertBody("Hello World")
            self.assertNoHeader("Connection")

            cherrypy.server.httpserver.interrupt = KeyboardInterrupt
            bus.block()

            self.assertEqual(db_connection.running, False)
            self.assertEqual(len(db_connection.threads), 0)
            self.assertEqual(bus.state, bus.states.EXITING)
        finally:
            self.persistent = False

        # Raise a keyboard interrupt in a page handler; on multithreaded
        # servers, this should occur in one of the worker threads.
        # This should raise a BadStatusLine error, since the worker
        # thread will just die without writing a response.
        bus.start()
        cherrypy.server.start()

        try:
            self.getPage("/ctrlc")
        except BadStatusLine:
            pass
        else:
            print(self.body)
            self.fail("AssertionError: BadStatusLine not raised")

        bus.block()
        self.assertEqual(db_connection.running, False)
        self.assertEqual(len(db_connection.threads), 0)

    def test_4_Autoreload(self):
        # Start the demo script in a new process
        p = helper.CPProcess(ssl=(self.scheme.lower()=='https'))
        p.write_conf(
                extra='test_case_name: "test_4_Autoreload"')
        p.start(imports='magicbus.test._test_states_demo')
        try:
            self.getPage("/start")
            start = float(self.body)

            # Give the autoreloader time to cache the file time.
            time.sleep(2)

            # Touch the file
            os.utime(os.path.join(thisdir, "_test_states_demo.py"), None)

            # Give the autoreloader time to re-exec the process
            time.sleep(2)
            host = cherrypy.server.socket_host
            port = cherrypy.server.socket_port
            cherrypy._cpserver.wait_for_occupied_port(host, port)

            self.getPage("/start")
            if not (float(self.body) > start):
                raise AssertionError("start time %s not greater than %s" %
                                     (float(self.body), start))
        finally:
            # Shut down the spawned process
            self.getPage("/exit")
        p.join()

    def test_5_Start_Error(self):
        # If a process errors during start, it should stop the bus
        # and exit with a non-zero exit code.
        p = helper.CPProcess(ssl=(self.scheme.lower()=='https'),
                             wait=True)
        p.write_conf(
                extra="""starterror: True
test_case_name: "test_5_Start_Error"
"""
        )
        p.start(imports='magicbus.test._test_states_demo')
        if p.exit_code == 0:
            self.fail("Process failed to return nonzero exit code.")


class PluginTests(helper.CPWebCase):
    def test_daemonize(self):
        if os.name not in ['posix']:
            return self.skip("skipped (not on posix) ")
        self.HOST = '127.0.0.1'
        self.PORT = 8081
        # Spawn the process and wait, when this returns, the original process
        # is finished.  If it daemonized properly, we should still be able
        # to access pages.
        p = helper.CPProcess(ssl=(self.scheme.lower()=='https'),
                             wait=True, daemonize=True,
                             socket_host='127.0.0.1',
                             socket_port=8081)
        p.write_conf(
             extra='test_case_name: "test_daemonize"')
        p.start(imports='magicbus.test._test_states_demo')
        try:
            # Just get the pid of the daemonization process.
            self.getPage("/pid")
            self.assertStatus(200)
            page_pid = int(self.body)
            self.assertEqual(page_pid, p.get_pid())
        finally:
            # Shut down the spawned process
            self.getPage("/exit")
        p.join()

        # Wait until here to test the exit code because we want to ensure
        # that we wait for the daemon to finish running before we fail.
        if p.exit_code != 0:
            self.fail("Daemonized parent process failed to exit cleanly.")


class SignalHandlingTests(helper.CPWebCase):
    def test_SIGHUP_tty(self):
        # When not daemonized, SIGHUP should shut down the server.
        try:
            from signal import SIGHUP
        except ImportError:
            return self.skip("skipped (no SIGHUP) ")

        # Spawn the process.
        p = helper.CPProcess(ssl=(self.scheme.lower()=='https'))
        p.write_conf(
                extra='test_case_name: "test_SIGHUP_tty"')
        p.start(imports='magicbus.test._test_states_demo')
        # Send a SIGHUP
        os.kill(p.get_pid(), SIGHUP)
        # This might hang if things aren't working right, but meh.
        p.join()

    def test_SIGHUP_daemonized(self):
        # When daemonized, SIGHUP should restart the server.
        try:
            from signal import SIGHUP
        except ImportError:
            return self.skip("skipped (no SIGHUP) ")

        if os.name not in ['posix']:
            return self.skip("skipped (not on posix) ")

        # Spawn the process and wait, when this returns, the original process
        # is finished.  If it daemonized properly, we should still be able
        # to access pages.
        p = helper.CPProcess(ssl=(self.scheme.lower()=='https'),
                             wait=True, daemonize=True)
        p.write_conf(
             extra='test_case_name: "test_SIGHUP_daemonized"')
        p.start(imports='magicbus.test._test_states_demo')

        pid = p.get_pid()
        try:
            # Send a SIGHUP
            os.kill(pid, SIGHUP)
            # Give the server some time to restart
            time.sleep(2)
            self.getPage("/pid")
            self.assertStatus(200)
            new_pid = int(self.body)
            self.assertNotEqual(new_pid, pid)
        finally:
            # Shut down the spawned process
            self.getPage("/exit")
        p.join()

    def test_SIGTERM(self):
        # SIGTERM should shut down the server whether daemonized or not.
        try:
            from signal import SIGTERM
        except ImportError:
            return self.skip("skipped (no SIGTERM) ")

        try:
            from os import kill
        except ImportError:
            return self.skip("skipped (no os.kill) ")

        # Spawn a normal, undaemonized process.
        p = helper.CPProcess(ssl=(self.scheme.lower()=='https'))
        p.write_conf(
                extra='test_case_name: "test_SIGTERM"')
        p.start(imports='magicbus.test._test_states_demo')
        # Send a SIGTERM
        os.kill(p.get_pid(), SIGTERM)
        # This might hang if things aren't working right, but meh.
        p.join()

        if os.name in ['posix']:
            # Spawn a daemonized process and test again.
            p = helper.CPProcess(ssl=(self.scheme.lower()=='https'),
                                 wait=True, daemonize=True)
            p.write_conf(
                 extra='test_case_name: "test_SIGTERM_2"')
            p.start(imports='magicbus.test._test_states_demo')
            # Send a SIGTERM
            os.kill(p.get_pid(), SIGTERM)
            # This might hang if things aren't working right, but meh.
            p.join()

    def test_signal_handler_unsubscribe(self):
        try:
            from signal import SIGTERM
        except ImportError:
            return self.skip("skipped (no SIGTERM) ")

        try:
            from os import kill
        except ImportError:
            return self.skip("skipped (no os.kill) ")

        # Spawn a normal, undaemonized process.
        p = helper.CPProcess(ssl=(self.scheme.lower()=='https'))
        p.write_conf(
            extra="""unsubsig: True
test_case_name: "test_signal_handler_unsubscribe"
""")
        p.start(imports='magicbus.test._test_states_demo')
        # Send a SIGTERM
        os.kill(p.get_pid(), SIGTERM)
        # This might hang if things aren't working right, but meh.
        p.join()

        # Assert the old handler ran.
        target_line = open(p.error_log, 'rb').readlines()[-10]
        if not ntob("I am an old SIGTERM handler.") in target_line:
            self.fail("Old SIGTERM handler did not run.\n%r" % target_line)

