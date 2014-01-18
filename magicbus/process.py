import atexit
import os
import sys
import threading
import warnings

try:
    import fcntl
except ImportError:
    max_files = 0
else:
    try:
        max_files = os.sysconf('SC_OPEN_MAX')
    except AttributeError:
        max_files = 1024

from magicbus import base

# Here I save the value of os.getcwd(), which, if I am imported early enough,
# will be the directory from which the startup script was run.  This is needed
# by _do_execv(), to change back to the original directory before execv()ing a
# new process.  This is a defense against the application having changed the
# current working directory (which could make sys.executable "not found" if
# sys.executable is a relative-path, and/or cause other problems).
_startup_cwd = os.getcwd()


class ProcessBus(base.Bus):
    """Process state-machine and messenger.

    All listeners for a given channel are guaranteed to be called even
    if others at the same channel fail. Each failure is logged, but
    execution proceeds on to the next listener. The only way to stop all
    processing from inside a listener is to raise SystemExit and stop the
    whole server.

    In general, there should only ever be a single ProcessBus object per process.
    Frameworks and site containers share a single ProcessBus object by publishing
    messages and subscribing listeners.

    The ProcessBus works as a finite state machine which models the current
    state of the process. ProcessBus methods move it from one state to another;
    those methods then publish to subscribed listeners on the channel for
    the new state.::

                            O
                            |
                            V
           STOPPING --> STOPPED --> EXITING -> X
              A   A         |
              |    \___     |
              |        \    |
              |         V   V
            STARTED <-- STARTING
    """

    execv = False
    max_cloexec_files = max_files

    def __init__(self):
        self.execv = False
        base.Bus.__init__(
            self,
            states=('STOPPED', 'STARTING', 'STARTED', 'STOPPING', 'EXITING'),
            state='STOPPED',
            channels=('start', 'stop', 'exit', 'graceful', 'log', 'main')
        )

    def _clean_exit(self):
        """An atexit handler which asserts the Bus is not running."""
        if self.state != self.states.EXITING:
            warnings.warn(
                "The main thread is exiting, but the Bus is in the %r state; "
                "shutting it down automatically now. You must either call "
                "bus.block() after start(), or call bus.exit() before the "
                "main thread exits." % self.state, RuntimeWarning)
            self.exit()

    def start(self):
        """Start all services."""
        atexit.register(self._clean_exit)

        self.state = self.states.STARTING
        self.log('Bus STARTING')
        try:
            self.publish('start')
            self.state = self.states.STARTED
            self.log('Bus STARTED')
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.log("Shutting down due to error in start listener:",
                     level=40, traceback=True)
            e_info = sys.exc_info()[1]
            try:
                self.exit()
            except:
                # Any stop/exit errors will be logged inside publish().
                pass
            # Re-raise the original error
            raise e_info

    def exit(self):
        """Stop all services and prepare to exit the process."""
        exitstate = self.state
        try:
            self.stop()

            self.state = self.states.EXITING
            self.log('Bus EXITING')
            self.publish('exit')
            # This isn't strictly necessary, but it's better than seeing
            # "Waiting for child threads to terminate..." and then nothing.
            self.log('Bus EXITED')
        except:
            # This method is often called asynchronously (whether thread,
            # signal handler, console handler, or atexit handler), so we
            # can't just let exceptions propagate out unhandled.
            # Assume it's been logged and just die.
            os._exit(70)  # EX_SOFTWARE

        if exitstate is self.states.STARTING:
            # exit() was called before start() finished, possibly due to
            # Ctrl-C because a start listener got stuck. In this case,
            # we could get stuck in a loop where Ctrl-C never exits the
            # process, so we just call os.exit here.
            os._exit(70)  # EX_SOFTWARE

    def restart(self):
        """Restart the process (may close connections).

        This method does not restart the process from the calling thread;
        instead, it stops the bus and asks the main thread to call execv.
        """
        self.execv = True
        self.exit()

    def graceful(self):
        """Advise all services to reload."""
        self.log('Bus graceful')
        self.publish('graceful')

    def block(self, interval=0.1):
        """Wait for the EXITING state, KeyboardInterrupt or SystemExit.

        This function is intended to be called only by the main thread.
        After waiting for the EXITING state, it also waits for all threads
        to terminate, and then calls os.execv if self.execv is True. This
        design allows another thread to call bus.restart, yet have the main
        thread perform the actual execv call (required on some platforms).
        """
        try:
            self.wait(self.states.EXITING, interval=interval, channel='main')
        except (KeyboardInterrupt, IOError):
            # The time.sleep call might raise
            # "IOError: [Errno 4] Interrupted function call" on KBInt.
            self.log('Keyboard Interrupt: shutting down bus')
            self.exit()
        except SystemExit:
            self.log('SystemExit raised: shutting down bus')
            self.exit()
            raise

        # Waiting for ALL child threads to finish is necessary on OS X.
        # See http://www.cherrypy.org/ticket/581.
        # It's also good to let them all shut down before allowing
        # the main thread to call atexit handlers.
        # See http://www.cherrypy.org/ticket/751.
        self.log("Waiting for child threads to terminate...")
        for t in threading.enumerate():
            if t != threading.currentThread() and t.isAlive():
                # Note that any dummy (external) threads are always daemonic.
                if not t.daemon:
                    self.log("Waiting for thread %s." % t.getName())
                    t.join()

        if self.execv:
            self._do_execv()

    def _do_execv(self):
        """Re-execute the current process.

        This must be called from the main thread, because certain platforms
        (OS X) don't allow execv to be called in a child thread very well.
        """
        args = sys.argv[:]
        self.log('Re-spawning %s' % ' '.join(args))

        if sys.platform[:4] == 'java':
            from _systemrestart import SystemRestart
            raise SystemRestart
        else:
            args.insert(0, sys.executable)
            if sys.platform == 'win32':
                args = ['"%s"' % arg for arg in args]

            os.chdir(_startup_cwd)
            if self.max_cloexec_files:
                self._set_cloexec()
            os.execv(sys.executable, args)

    def _set_cloexec(self):
        """Set the CLOEXEC flag on all open files (except stdin/out/err).

        If self.max_cloexec_files is an integer (the default), then on
        platforms which support it, it represents the max open files setting
        for the operating system. This function will be called just before
        the process is restarted via os.execv() to prevent open files
        from persisting into the new process.

        Set self.max_cloexec_files to 0 to disable this behavior.
        """
        for fd in range(3, self.max_cloexec_files):  # skip stdin/out/err
            try:
                flags = fcntl.fcntl(fd, fcntl.F_GETFD)
            except IOError:
                continue
            fcntl.fcntl(fd, fcntl.F_SETFD, flags | fcntl.FD_CLOEXEC)

    def stop(self):
        """Stop all services."""
        self.state = self.states.STOPPING
        self.log('Bus STOPPING')
        self.publish('stop')
        self.state = self.states.STOPPED
        self.log('Bus STOPPED')

    def start_with_callback(self, func, args=None, kwargs=None):
        """Start 'func' in a new thread T, then start self (and return T)."""
        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}
        args = (func,) + args

        def _callback(func_, *a, **kw):
            self.wait(self.states.STARTED)
            func_(*a, **kw)
        t = threading.Thread(target=_callback, args=args, kwargs=kwargs)
        t.setName('Bus Callback ' + t.getName())
        t.start()

        self.start()

        return t
