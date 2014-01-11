from magicbus import bus
from magicbus.plugins import servers
from magicbus.test import assertEqual, WebService, WebHandler

# from magicbus.plugins import loggers
# loggers.StdoutLogger(bus).subscribe()


class Handler(WebHandler):

    bus = bus

    def do_GET(self):
        if self.path == '/':
            self.respond("Hello World")
        elif self.path == '/ctrlc':
            self.respond("okey-doke")
            raise KeyboardInterrupt
        elif self.path == '/exit':
            self.respond("ok")
            self.bus.exit()
        else:
            self.respond(status=404)
service = WebService(handler_class=Handler)
adapter = servers.ServerPlugin(bus, service, service.address)
adapter.subscribe()


class TestServers(object):

    def test_keyboard_interrupt(self):
        # Raise a keyboard interrupt in the HTTP server's main thread.
        bus.start()
        resp = service.do_GET("/ctrlc")
        assertEqual(resp.status, 200)
        bus.block()
        assertEqual(bus.state, bus.states.EXITING)
