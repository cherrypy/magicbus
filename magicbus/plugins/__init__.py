"""Site services for use with a Web Site Process Bus."""


class SimplePlugin(object):
    """Plugin base class which auto-subscribes methods for known channels."""
    
    bus = None
    """A :class:`Bus <magicbus.wspbus.Bus>`."""
    
    def __init__(self, bus):
        self.bus = bus
    
    def subscribe(self):
        """Register this object as a (multi-channel) listener on the bus."""
        for channel in self.bus.listeners:
            # Subscribe self.start, self.exit, etc. if present.
            method = getattr(self, channel, None)
            if method is not None:
                self.bus.subscribe(channel, method)
    
    def unsubscribe(self):
        """Unregister this object as a listener on the bus."""
        for channel in self.bus.listeners:
            # Unsubscribe self.start, self.exit, etc. if present.
            method = getattr(self, channel, None)
            if method is not None:
                self.bus.unsubscribe(channel, method)
