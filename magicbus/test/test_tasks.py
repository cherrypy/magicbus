from magicbus.plugins import tasks
from magicbus.test import assertEqual, WebAdapter, WebService, WebHandler

from magicbus.process import ProcessBus


class TestTasks(object):

    def test_thread_manager(self):
        bus = ProcessBus()

        class Handler(WebHandler):

            def do_GET(self):
                if self.path == '/':
                    self.respond('Hello World')
                else:
                    self.respond(status=404)
        Handler.bus = bus

        service = WebService(address=('127.0.0.1', 38001),
                             handler_class=Handler)
        WebAdapter(bus, service).subscribe()

        tm = tasks.ThreadManager(bus)
        tm.subscribe()
        assertEqual(len(tm.threads), 0)

        # Test server start
        bus.transition('RUN')
        try:
            assertEqual(bus.state, 'RUN')
            assertEqual(service.ready, True)
            assertEqual(len(tm.threads), 0)

            assertEqual(service.do_GET('/').read(), b'Hello World')
            assertEqual(len(tm.threads), 1)

            # Test bus stop. This will also stop the WebService.
            bus.transition('IDLE')
            assertEqual(bus.state, 'IDLE')

            # Verify that our custom stop function was called
            assertEqual(len(tm.threads), 0)
        finally:
            bus.transition('EXITED')
