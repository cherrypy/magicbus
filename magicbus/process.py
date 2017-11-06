import os
import threading

from magicbus import base
from magicbus.plugins import lifecycle


class ProcessBus(base.Bus):
    """A Bus subclass for managing the state of a process.

    In general, there should only ever be a single ProcessBus object
    per process. Frameworks and site containers share a single ProcessBus
    by publishing messages and subscribing listeners.

    The ProcessBus works as a state machine which models the current
    state of the process. ProcessBus methods transition it from one state
    to another; those methods publish to subscribed listeners on the
    new state's channel after setting the new state. A simplified model
    might be::

              _start_
             /       \
            V         \
           RUN       IDLE --exit--> EXITED
            \         A
             \_______/
               stop

    But of course, nothing is ever so easy in the engineering world.
    In reality, start or stop could throw an error, or even fail to
    return. We *always* need an error handler (even if many states
    share the same one), and we *always* need to allow a transition,
    not just from one final state to another, but from the middle
    of start/stop to a new state. We model this by elevating each
    of our naive transitions to its own intermediate state, and adding
    error states. That is::

         XXXXXXXXXXXXXXXX START              XXXXXX-> EXIT_ERROR
         |              /   |   A            X            |
         V             V    |    \           X            V
    START_ERROR <-XX RUN    |    IDLE ----> EXIT ----> EXITED ---> X
         |             \    |    A| A
         |              V   V   / |  \
         +---------------> STOP   X    ENTER <--- INITIAL
                            X     X      X
                            |     |      X
                            V     V      X
                           STOP_ERROR <-XX

    Now the movement to the "RUN" state from the "IDLE" state encompasses
    two transitions, four if you count error transitions.
    """

    throws = (KeyboardInterrupt, SystemExit)

    def __init__(self):
        base.Bus.__init__(
            self,
            # Transitions from k -> v. Note that this does *not*
            # include any transitions triggered by errors;
            # those are in the "error" dict below so that
            # 1) try/except blocks can take error transitions but also
            # 2) transition() will *not* take error transitions.
            # However, we *do* include transitions *away from* error states.
            transitions={
                'INITIAL': 'ENTER',
                'ENTER': 'IDLE',
                'START': ('RUN', 'STOP'),
                'RUN': 'STOP',
                'START_ERROR': 'STOP',
                'STOP': 'IDLE',
                'IDLE': ('START', 'EXIT'),
                'STOP_ERROR': 'EXIT',
                'EXIT': 'EXITED',
                'EXIT_ERROR': 'EXITED',
            },
            # A dict whose keys are states. Exceptions raised during
            # the execution of those states move the machine to the
            # state named by the corresponding value.
            errors={
                'ENTER': 'STOP_ERROR',
                'START': 'START_ERROR',
                'RUN': 'START_ERROR',
                'STOP': 'STOP_ERROR',
                'IDLE': 'STOP_ERROR',
                'EXIT': 'EXIT_ERROR'
            },
            initial_state='INITIAL',
            extra_channels=('log', 'main', 'execv')
        )

        self.subscribe('START_ERROR', self.START_ERROR)
        self.subscribe('STOP_ERROR', self.STOP_ERROR)
        self.subscribe('EXIT_ERROR', self.EXIT_ERROR)

        self.thread_wait = lifecycle.ThreadWait(self)
        self.thread_wait.subscribe()
        self.clean_exit = lifecycle.CleanExit(self)
        self.clean_exit.subscribe()

    def START_ERROR(self, *exc_info):
        self.log('Exiting due to error in start listener:',
                 level=40, traceback=exc_info)
        self.transition('EXITED')

    def STOP_ERROR(self, *exc_info):
        self.log('Exiting due to error in stop listener:',
                 level=40, traceback=exc_info)
        self.transition('EXITED')

    def EXIT_ERROR(self, *exc_info):
        # This method is often called asynchronously (whether thread,
        # signal handler, console handler, or atexit handler), so we
        # can't just let exceptions propagate out unhandled.
        # Log it and just die.
        self.log("Exiting due to error in 'exit' listener:",
                 level=40, traceback=exc_info)
        os._exit(70)  # EX_SOFTWARE

    def restart(self):
        """Restart the process (may close connections).

        This method does not restart the process from the calling thread;
        instead, it stops the bus and asks the main thread to call execv.
        """
        from magicbus.plugins.lifecycle import Execv
        Execv(self).subscribe()
        self.transition('EXITED')

    def graceful(self):
        """Move to the IDLE state, then back to RUN."""
        self.transition('IDLE')
        self.transition('RUN')

    def block(self, interval=0.1, sleep=False):
        """Wait for the EXITED state, KeyboardInterrupt or SystemExit.

        This function is intended to be called only by the main thread.
        After waiting for the EXITED state, it also waits for all threads
        to terminate, and then calls publish('execv'). This design allows
        another thread to call bus.restart, yet have the main thread perform
        the actual execv call (required on some platforms).
        """
        try:
            self.wait('EXITED', interval=interval, channel='main', sleep=sleep)
        except (KeyboardInterrupt, IOError):
            # The time.sleep call might raise
            # "IOError: [Errno 4] Interrupted function call" on KBInt.
            self.log('Keyboard Interrupt: shutting down bus')
            self.transition('EXITED')
        except SystemExit:
            self.log('SystemExit raised: shutting down bus')
            self.transition('EXITED')
            raise

        self.publish('execv')

    def start_with_callback(self, func, args=None, kwargs=None):
        """Start 'func' in a new thread T, then start self (and return T)."""
        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}
        args = (func,) + args

        def _callback(func_, *a, **kw):
            self.wait('RUN')
            func_(*a, **kw)
        t = threading.Thread(target=_callback, args=args, kwargs=kwargs)
        t.setName('Bus Callback ' + t.getName())
        t.start()

        self.transition('RUN')

        return t
