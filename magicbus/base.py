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
import os
import random
try:
    import select
except ImportError:
    select = None
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
        return 'State(%s)' % repr(self.name)


class StateEnum(object):
    """An object with enumerated state attributes."""
    pass


class Graph(dict):
    """A map of {(A, C): B} where B is next in the shortest path from A to C.

    Each key is a 2-tuple of nodes (A, C), and the corresponding value is
    the next node B to take on the shortest path between them. For example,
    the Graph {("A", "B"): "B", ("A", "C"): "B"} declares that the shortest
    path from A to B is directly to B, while the shortest path from
    A to C starts by moving to B. Calling code can find the shortest path
    [Pa, ..., Pz] by iteratively calling self.get((Pn, Pz)).

    Any pair (A, B) not in the map has no path.
    """

    @property
    def states(self):
        """The set of all states in the graph."""
        s = set(self.values())
        for a, b in self:
            s.add(a)
            s.add(b)
        return s

    @classmethod
    def from_edges(cls, edges):
        """Form a Graph instance from the given {from: (to1, to2)} dict.

        The given 'edges' dictionary includes a key for each node from
        which a transition might originate. The corresponding value is
        either a node or a tuple of nodes; the graph includes an edge
        from the key node to each node in the value. For example, the
        dict {"A": "B", "B", ("C", "D")} defines 3 edges: A to B,
        B to C and B to D.
        """
        # Modified Floyd-Warshall algorithm, where all weights are 1.
        # Rather than a sparse matrix, we build a map {(A, B): next}
        # where the "next" value is the next node on the shortest path
        # from A to B. Any pair (a, b) not in the map has no path.
        # Thereby, calling code can find the shortest path [Pn, Pn+1, ...]
        # by iteratively calling self.get((Pn, Pn+1), None)
        if edges is None:
            edges = {}
        states = set()

        distances = {}
        next = {}
        for k, v in edges.items():
            states.add(k)
            distances[(k, k)] = 0

            if not isinstance(v, (list, tuple)):
                v = (v,)
            for s in v:
                states.add(s)
                # Store the edge from k to s.
                distances[(k, s)] = 1
                next[(k, s)] = s

        for k in states:
            for i in states:
                for j in states:
                    segment1 = distances.get((i, k))
                    if segment1 is None:
                        continue
                    segment2 = distances.get((k, j))
                    if segment2 is None:
                        continue
                    candidate_distance = segment1 + segment2

                    curpair = (i, j)
                    current_distance = distances.get(curpair)
                    if current_distance is None or current_distance > candidate_distance:
                        # print ("(%s -> %s) %s > (%s -> %s -> %s) %s" %
                        #        (i, j, current_distance,
                        #         i, k, j, candidate_distance))
                        distances[curpair] = candidate_distance
                        next[curpair] = next.get((i, k), k)

        return cls(next)


class Bus(object):
    """State machine and pub/sub messenger.

    If the 'select' module is present (POSIX systems), then select.select()
    (on an os.pipe) will be used in self.wait instead of time.sleep().
    """

    publish_exception_class = ChannelFailures

    def __init__(self, transitions=None, errors=None,
                 initial_state=None, extra_channels=None, id=None):
        if not isinstance(transitions, Graph):
            transitions = Graph.from_edges(transitions)
        self.transitions = transitions
        self.errors = errors
        self.state = initial_state

        self.listeners = dict((c, set()) for c in self.states)
        if extra_channels is None:
            extra_channels = ('log',)
        for c in extra_channels:
            self.listeners[c] = set()

        if id is None:
            id = hex(random.randint(0, sys.maxsize))[-8:]
        self.id = id
        self._priorities = {}
        self._state_transition_pipes = set()

    @property
    def states(self):
        return self.transitions.states

    def transition(self, desired_state):
        """Move to the desired state. Return output (list of lists)."""
        output = []
        while self.state != desired_state:
            next_state = self.transitions.get((self.state, desired_state))
            if next_state is None:
                # Cannot proceed any further.
                break
            output.append(self._transition(next_state))
        return output

    def _transition(self, newstate, *args, **kwargs):
        """Transition and publish to the new state. Return output list.

        This method should only be called if there is a registered
        1-hop transition between the current state and the new state.

        Any *args or **kwargs will be passed to the publish call.
        Error transitions, for example, pass *sys.exc_info() as
        positional arguments to all error listeners.
        """
        try:
            self.state = newstate

            # Write to any pipes created by threads calling self.wait().
            # Use list() to avoid "Set changed size during iteration" errors.
            for read_fd, write_fd in list(self._state_transition_pipes):
                os.write(write_fd, b"1")

            # Note: logging here means 1) the initial transition
            # will not be logged if loggers are set up in the initial
            # transition! and 2) the final transition will not be logged
            # if loggers are torn down in the penultimate transition!
            # This is why, for example, the included loggers are
            # "always on" rather than listening for start/stop themselves.
            self.log('Bus state: %s' % newstate)

            return self.publish(newstate, *args, **kwargs)
        except self.throws:
            raise
        except:
            if newstate in self.errors:
                # Note we are calling the private method here;
                # we do not allow a multi-hop transition to an error
                # state, because we want to pass the exc_info around.
                self._transition(self.errors[newstate], *sys.exc_info())
            else:
                raise

    def subscribe(self, channel, callee, priority=None):
        """Add the given callee at the given channel (if not present)."""
        if channel not in self.listeners:
            self.listeners[channel] = set()
        self.listeners[channel].add(callee)

        if priority is None:
            priority = getattr(callee, 'priority', 50)
        self._priorities[(channel, callee)] = priority

    def unsubscribe(self, channel, callee):
        """Discard the given callee (if present)."""
        listeners = self.listeners.get(channel)
        if listeners and callee in listeners:
            listeners.discard(callee)
            del self._priorities[(channel, callee)]

    def clear(self):
        """Discard all subscribed callees."""
        # Use items() as a snapshot instead of while+pop so that callers
        # can be slightly lax in subscribing new listeners while the old
        # ones are being removed.
        for channel, listeners in self.listeners.items():
            for callee in list(listeners):
                listeners.discard(callee)
                del self._priorities[(channel, callee)]

    def publish(self, channel, *args, **kwargs):
        """Return output of all subscribers for the given channel."""
        if channel not in self.listeners:
            return []

        exc = self.publish_exception_class()
        output = []

        items = [(self._priorities[(channel, listener)], listener)
                 for listener in self.listeners[channel]]
        items.sort(key=lambda item: item[0])
        for priority, listener in items:
            try:
                # Listeners are guaranteed to run even if others on the
                # the same channel fail. We will still log the failure,
                # but proceed on to the next listener. The only way
                # to stop all processing from inside a listener is
                # to raise one of the exceptions in self.throws
                # (e.g. SystemExit).
                result = listener(*args, **kwargs)
                output.append(result)
            except self.throws:
                # e = sys.exc_info()[1]
                # # If we have previous errors ensure the exit code is non-zero
                # if exc and e.code == 0:
                #     e.code = 1
                raise
            except:
                exc.handle_exception()

                if channel == 'log':
                    # Assume any further messages to 'log' will fail.
                    pass
                else:
                    self.log('Error in %r listener %r' % (channel, listener),
                             level=40, traceback=True)
        if exc:
            raise exc
        return output

    def wait(self, state, interval=0.1, channel=None, sleep=False):
        """Poll for the given state(s) at intervals; publish to channel.

        If sleep is True, the calling thread loops, sleeping for the given
        interval each time, then returning only when the bus state is
        one of the given states to wait for.

        If sleep is False (the default) and the operating system supports
        I/O multiplexing via the 'select' module, then an anonymous pipe
        will be used to signal the waiting thread to wake up whenever
        the state transitions. This allows the waiting thread to return
        when the bus shuts down, for example, rather than waiting for
        the sleep interval to elapse first. Each thread that calls wait()
        creates a new pipe, so if file descriptors are in short supply
        on your system you might need to use sleep instead.
        """
        if isinstance(state, (tuple, list)):
            _states_to_wait_for = state
        else:
            _states_to_wait_for = [state]

        if select:
            pipe = os.pipe()
            read_fd, write_fd = pipe
            self._state_transition_pipes.add(pipe)

        def _wait():
            try:
                while self.state not in _states_to_wait_for:
                    if select:
                        try:
                            r, w, x = select.select([read_fd], [], [], interval)
                            if r:
                                os.read(read_fd, 1)
                        except (select.error, OSError):
                            # Interrupted due to a signal (being handled by some
                            # other thread). No need to panic, here, just check
                            # the new state and proceed/return.
                            pass
                    else:
                        time.sleep(interval)
                    self.publish(channel)
            finally:
                self._state_transition_pipes.discard(pipe)
                os.close(read_fd)
                os.close(write_fd)

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

    def log(self, msg='', level=20, traceback=False):
        """Log the given message. Append the last traceback if requested."""
        if traceback:
            if traceback is True:
                exc_info = sys.exc_info()
            else:
                exc_info = traceback
            msg += '\n' + ''.join(_traceback.format_exception(*exc_info))
        self.publish('log', msg, level)
