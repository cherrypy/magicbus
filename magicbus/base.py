"""A pub/sub Bus for managing states.

A Bus object is used to contain and manage behavior for any system
of diverse components. A Bus object provides a place for frameworks
to register code that runs in response to events, or which controls
or otherwise interacts with the components.

The Bus object in this package uses topic-based publish-subscribe
messaging to accomplish all this. Frameworks and site containers
are free to define their own channels. If a message is sent to a
channel that has not been defined or has no listeners, there is no effect.
"""

import sys
import time
import traceback as _traceback


class ChannelFailures(Exception):
    """Exception raised when errors occur in a listener during .publish()."""
    delimiter = '\n'

    def __init__(self, *args, **kwargs):
        super(ChannelFailures, self).__init__(*args, **kwargs)
        self._exceptions = list()

    def handle_exception(self):
        """Append the current exception to self."""
        self._exceptions.append(sys.exc_info()[1])

    def get_instances(self):
        """Return a list of seen exception instances."""
        return self._exceptions[:]

    def __str__(self):
        exception_strings = map(repr, self.get_instances())
        return self.delimiter.join(exception_strings)

    __repr__ = __str__

    def __bool__(self):
        return bool(self._exceptions)
    __nonzero__ = __bool__


class State(object):

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return "State(%s)" % repr(self.name)


class StateEnum(object):
    """An object with enumerated state attributes."""
    pass


class Bus(object):
    """State machine and pub/sub messenger.

    All listeners for a given channel are guaranteed to be called even
    if others at the same channel fail. Each failure is logged, but
    execution proceeds on to the next listener. The only way to stop all
    processing from inside a listener is to raise SystemExit and stop the
    whole server.
    """

    def __init__(self, states=None, state=None, channels=None):
        if isinstance(states, StateEnum):
            self.states = states
        else:
            self.states = StateEnum()
            for s in states or []:
                setattr(self.states, s, State(s))

        if state is not None:
            state = getattr(self.states, state)
        self.state = state

        if channels is None:
            channels = ('log',)
        self.listeners = dict((channel, set()) for channel in channels)

        self._priorities = {}
        self.debug = False

    def subscribe(self, channel, callback, priority=None):
        """Add the given callback at the given channel (if not present)."""
        if channel not in self.listeners:
            self.listeners[channel] = set()
        self.listeners[channel].add(callback)

        if priority is None:
            priority = getattr(callback, 'priority', 50)
        self._priorities[(channel, callback)] = priority

    def unsubscribe(self, channel, callback):
        """Discard the given callback (if present)."""
        listeners = self.listeners.get(channel)
        if listeners and callback in listeners:
            listeners.discard(callback)
            del self._priorities[(channel, callback)]

    def clear(self):
        """Discard all subscribed callbacks."""
        # Use items() as a snapshot instead of while+pop so that callers
        # can be slightly lax in subscribing new listeners while the old
        # ones are being removed.
        for channel, listeners in self.listeners.items():
            for callback in list(listeners):
                listeners.discard(callback)
                del self._priorities[(channel, callback)]

    def publish(self, channel, *args, **kwargs):
        """Return output of all subscribers for the given channel."""
        if channel not in self.listeners:
            return []

        exc = ChannelFailures()
        output = []

        items = [(self._priorities[(channel, listener)], listener)
                 for listener in self.listeners[channel]]
        items.sort(key=lambda item: item[0])
        for priority, listener in items:
            try:
                if self.debug and channel != 'log':
                    self.log("Publishing to %s: %s(*%s, **%s)" %
                             (channel, listener, args, kwargs))
                result = listener(*args, **kwargs)
                if self.debug and channel != 'log':
                    self.log("Publishing to %s: %s(*%s, **%s) = %s" %
                             (channel, listener, args, kwargs, result))
                output.append(result)
            except KeyboardInterrupt:
                raise
            except SystemExit:
                e = sys.exc_info()[1]
                # If we have previous errors ensure the exit code is non-zero
                if exc and e.code == 0:
                    e.code = 1
                raise
            except:
                exc.handle_exception()
                if channel == 'log':
                    # Assume any further messages to 'log' will fail.
                    pass
                else:
                    self.log("Error in %r listener %r" % (channel, listener),
                             level=40, traceback=True)
        if exc:
            raise exc
        return output

    def wait(self, state, interval=0.1, channel=None):
        """Poll for the given state(s) at intervals; publish to channel."""
        if isinstance(state, (tuple, list)):
            _states_to_wait_for = state
        else:
            _states_to_wait_for = [state]

        def _wait():
            while self.state not in _states_to_wait_for:
                time.sleep(interval)
                self.publish(channel)

        # From http://psyco.sourceforge.net/psycoguide/bugs.html:
        # "The compiled machine code does not include the regular polling
        # done by Python, meaning that a KeyboardInterrupt will not be
        # detected before execution comes back to the regular Python
        # interpreter. Your program cannot be interrupted if caught
        # into an infinite Psyco-compiled loop."
        try:
            sys.modules['psyco'].cannotcompile(_wait)
        except (KeyError, AttributeError):
            pass

        _wait()

    def log(self, msg="", level=20, traceback=False):
        """Log the given message. Append the last traceback if requested."""
        if traceback:
            msg += "\n" + "".join(_traceback.format_exception(*sys.exc_info()))
        self.publish('log', msg, level)
