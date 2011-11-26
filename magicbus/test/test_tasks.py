from magicbus._compat import BadStatusLine, ntob
import os
import sys
import threading
import time

from magicbus import bus
from magicbus.plugins import tasks
from magicbus.test import assertEqual
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

    def __call__(self, path):
        self.bus.publish('acquire_thread')
        if path == '/':
            return "Hello World"
        elif path == '/graceful':
            bus.graceful()
            return "app was (gracefully) restarted succesfully"
        elif path == '/ctrlc':
            raise KeyboardInterrupt
        raise ValueError("Unknown URI")


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


class TestTasks(object):

    def test_thread_manager(self):
        bus.clear()
        thread_manager = tasks.ThreadManager(bus)
        thread_manager.subscribe()
        service = WebService(bus)
        service.subscribe()
        db = Dependency(bus)
        db.subscribe()

        # Our db should not be running
        assertEqual(db.running, False)
        assertEqual(db.startcount, 0)
        assertEqual(len(db.threads), 0)

        # Test server start
        bus.start()
        assertEqual(bus.state, bus.states.STARTED)
        assertEqual(service.running, True)

        # The db should be running now
        assertEqual(db.running, True)
        assertEqual(db.startcount, 1)
        assertEqual(len(db.threads), 0)

        assertEqual(service("/"), "Hello World")
        assertEqual(len(db.threads), 1)

        # Test bus stop. This will also stop the WebService.
        bus.stop()
        assertEqual(bus.state, bus.states.STOPPED)

        # Verify that our custom stop function was called
        assertEqual(db.running, False)
        assertEqual(len(db.threads), 0)

        # Block the main thread now and verify that exit() works.
        def exittest():
            assertEqual(service("/"), "Hello World")
            bus.exit()
        bus.start_with_callback(exittest)
        bus.block()
        assertEqual(bus.state, bus.states.EXITING)

    def test_restart(self):
        bus.clear()
        thread_manager = tasks.ThreadManager(bus)
        thread_manager.subscribe()
        service = WebService(bus)
        service.subscribe()
        db = Dependency(bus)
        db.subscribe()

        bus.start()

        # The db should be running now
        assertEqual(db.running, True)
        grace = db.gracecount

        assertEqual(service("/"), "Hello World")
        assertEqual(len(db.threads), 1)

        # Test server restart from this thread
        bus.graceful()
        assertEqual(bus.state, bus.states.STARTED)

        assertEqual(service("/"), "Hello World")
        assertEqual(db.running, True)
        assertEqual(db.gracecount, grace + 1)
        assertEqual(len(db.threads), 1)

        # Test server restart from inside a page handler
        result = service("/graceful")
        assertEqual(bus.state, bus.states.STARTED)
        assertEqual(result, "app was (gracefully) restarted succesfully")
        assertEqual(db.running, True)
        assertEqual(db.gracecount, grace + 2)
        # Since we are requesting synchronously, is only one thread used?
        # Note that the "/graceful" request has been flushed.
        assertEqual(len(db.threads), 0)

        bus.stop()
        assertEqual(bus.state, bus.states.STOPPED)
        assertEqual(db.running, False)
        assertEqual(len(db.threads), 0)

