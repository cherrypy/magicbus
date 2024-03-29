from magicbus.process import ProcessBus
from magicbus.plugins import servers
from magicbus.test import WebService, WebHandler

# from magicbus.plugins import loggers
# loggers.StdoutLogger(bus).subscribe()


class Handler(WebHandler):

    def do_GET(self):
        if self.path == '/':
            self.respond('Hello World')
        elif self.path == '/ctrlc':
            self.respond('okey-doke')
            raise KeyboardInterrupt
        else:
            self.respond(status=404)


def test_keyboard_interrupt():
    bus = ProcessBus()

    Handler.bus = bus
    service = WebService(address=('127.0.0.1', 38002),
                         handler_class=Handler)
    adapter = servers.ServerPlugin(bus, service, service.address)
    adapter.subscribe()

    # Raise a keyboard interrupt in the HTTP server's main thread.
    bus.transition('RUN')
    resp = service.do_GET('/ctrlc')
    assert resp.status == 200
    bus.block()
    assert bus.state == 'EXITED'
