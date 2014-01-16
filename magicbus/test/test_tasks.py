from magicbus import bus
from magicbus.plugins import tasks
from magicbus.test import assertEqual, WebAdapter, WebService, WebHandler


class Handler(WebHandler):

    bus = bus

    def do_GET(self):
        if self.path == '/':
            self.respond("Hello World")
        elif self.path == '/graceful':
            self.bus.graceful()
            self.respond("app was (gracefully) restarted succesfully")
        elif self.path == '/ctrlc':
            raise KeyboardInterrupt
        else:
            self.respond(status=404)


class TestTasks(object):

    def test_thread_manager(self):
        bus.clear()

        service = WebService(address=('127.0.0.1', 38001),
                             handler_class=Handler)
        WebAdapter(bus, service).subscribe()

        tm = tasks.ThreadManager(bus)
        tm.subscribe()
        assertEqual(len(tm.threads), 0)

        # Test server start
        bus.start()
        try:
            assertEqual(bus.state, bus.states.STARTED)
            assertEqual(service.ready, True)
            assertEqual(len(tm.threads), 0)

            assertEqual(service.do_GET("/").read(), b"Hello World")
            assertEqual(len(tm.threads), 1)

            # Test bus stop. This will also stop the WebService.
            bus.stop()
            assertEqual(bus.state, bus.states.STOPPED)

            # Verify that our custom stop function was called
            assertEqual(len(tm.threads), 0)
        finally:
            bus.exit()
