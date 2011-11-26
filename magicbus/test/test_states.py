from magicbus._compat import BadStatusLine, ntob
import os
import sys
import threading
import time

from magicbus import bus
thisdir = os.path.join(os.getcwd(), os.path.dirname(__file__))


class StateTests(object):

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

