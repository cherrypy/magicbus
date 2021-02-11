from magicbus.plugins import tasks
from magicbus.test import WebAdapter, WebService, WebHandler

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
        assert len(tm.threads) == 0

        # Test server start
        bus.transition('RUN')
        try:
            assert bus.state == 'RUN'
            assert service.ready is True
            assert len(tm.threads) == 0

            assert service.do_GET('/').read() == b'Hello World'
            assert len(tm.threads) == 1

            # Test bus stop. This will also stop the WebService.
            bus.transition('IDLE')
            assert bus.state == 'IDLE'

            # Verify that our custom stop function was called
            assert len(tm.threads) == 0
        finally:
            bus.transition('EXITED')
