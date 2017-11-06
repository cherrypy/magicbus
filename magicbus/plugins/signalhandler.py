"""Signal handling for the Process Bus."""

import os
import signal as _signal
import sys

from magicbus.compat import basestring


class SignalHandler(object):
    """Register bus channels (and listeners) for system signals.

    You can modify what signals your application listens for, and what it does
    when it receives signals, by modifying :attr:`SignalHandler.handlers`,
    a dict of {signal name: callback} pairs. The default set is::

        handlers = {'SIGTERM': self.bus.transition("EXITED"),
                    'SIGHUP': self.handle_SIGHUP,
                    'SIGUSR1': self.bus.transition("IDLE"); self.bus.transition("RUN"),
                   }

    The :func:`SignalHandler.handle_SIGHUP`` method calls execv if the process
    is daemonized, but exits if the process is attached to a TTY. This is
    because Unix window managers tend to send SIGHUP to terminal windows
    when the user closes them.

    Feel free to add signals which are not available on every platform. The
    :class:`SignalHandler` will ignore errors raised from attempting to
    register handlers for unknown signals.
    """

    handlers = {}
    """A map from signal names (e.g. 'SIGTERM') to handlers."""

    signals = {}
    """A map from signal numbers to names."""

    for k, v in vars(_signal).items():
        if k.startswith('SIG') and not k.startswith('SIG_'):
            signals[v] = k
    del k, v

    def __init__(self, bus):
        self.bus = bus
        # Set default handlers
        self.handlers = {'SIGTERM': self.handle_SIGTERM,
                         'SIGHUP': self.handle_SIGHUP,
                         'SIGUSR1': self.bus.graceful,
                         }

        if sys.platform[:4] == 'java':
            del self.handlers['SIGUSR1']
            self.handlers['SIGUSR2'] = self.bus.graceful
            self.bus.log('SIGUSR1 cannot be set on the JVM platform. '
                         'Using SIGUSR2 instead.')
            self.handlers['SIGINT'] = self._jython_SIGINT_handler

        self._previous_handlers = {}

    def _jython_SIGINT_handler(self, signum=None, frame=None):
        # See http://bugs.jython.org/issue1313
        self.bus.log('Keyboard Interrupt: shutting down bus')
        self.bus.transition('EXITED')

    def subscribe(self):
        self.bus.subscribe('ENTER', self.subscribe_handlers)

    def subscribe_handlers(self):
        """Subscribe self.handlers to signals."""
        for sig, func in self.handlers.items():
            try:
                self.set_handler(sig, func)
            except ValueError:
                pass
    # Only run after Daemonizer.ENTER (65)
    subscribe_handlers.priority = 70

    def unsubscribe(self):
        """Unsubscribe self.handlers from signals."""
        for signum, handler in self._previous_handlers.items():
            signame = self.signals[signum]

            if handler is None:
                self.bus.log('Restoring %s handler to SIG_DFL.' % signame)
                handler = _signal.SIG_DFL
            else:
                self.bus.log('Restoring %s handler %r.' % (signame, handler))

            try:
                our_handler = _signal.signal(signum, handler)
                if our_handler is None:
                    self.bus.log('Restored old %s handler %r, but our '
                                 'handler was not registered.' %
                                 (signame, handler), level=30)
            except ValueError:
                self.bus.log('Unable to restore %s handler %r.' %
                             (signame, handler), level=40, traceback=True)

    def set_handler(self, signal, listener=None):
        """Subscribe a handler for the given signal (number or name).

        If the optional 'listener' argument is provided, it will be
        subscribed as a listener for the given signal's channel.

        If the given signal name or number is not available on the current
        platform, ValueError is raised.
        """
        if isinstance(signal, basestring):
            signum = getattr(_signal, signal, None)
            if signum is None:
                raise ValueError('No such signal: %r' % signal)
            signame = signal
        else:
            try:
                signame = self.signals[signal]
            except KeyError:
                raise ValueError('No such signal: %r' % signal)
            signum = signal

        prev = _signal.signal(signum, self._handle_signal)
        self._previous_handlers[signum] = prev

        if listener is not None:
            self.bus.log('Listening for %s.' % signame)
            self.bus.subscribe(signame, listener)

    def _handle_signal(self, signum=None, frame=None):
        """Python signal handler (self.set_handler subscribes it for you)."""
        signame = self.signals[signum]
        self.bus.log('Caught signal %s.' % signame)
        self.bus.publish(signame)

    def handle_SIGTERM(self):
        """Transition to the EXITED state."""
        self.bus.log('SIGTERM caught. Exiting.')
        self.bus.transition('EXITED')

    def handle_SIGHUP(self):
        """Restart if daemonized, else exit."""
        if os.isatty(sys.stdin.fileno()):
            # not daemonized (may be foreground or background)
            self.bus.log('SIGHUP caught but not daemonized. Exiting.')
            self.bus.transition('EXITED')
        else:
            self.bus.log('SIGHUP caught while daemonized. Restarting.')
            self.bus.restart()
