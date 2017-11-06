"""Process lifecycle plugins."""

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

from magicbus import plugins


class CleanExit(plugins.SimplePlugin):

    def ENTER(self):
        atexit.register(self._clean_exit)

    def _clean_exit(self):
        """An atexit handler which asserts the Bus is not running."""
        if self.bus.state != 'EXITED':
            warnings.warn(
                'The main thread is exiting, but the Bus is in the %r state; '
                'shutting it down automatically now. You must either call '
                'bus.block() after start(), or call bus.exit() before the '
                'main thread exits.' % self.bus.state, RuntimeWarning)
            self.bus.transition('EXITED')


class ThreadWait(plugins.SimplePlugin):

    def EXIT(self):
        # Waiting for ALL child threads to finish is necessary on OS X.
        # See http://www.cherrypy.org/ticket/581.
        # It's also good to let them all shut down before allowing
        # the main thread to call atexit handlers.
        # See http://www.cherrypy.org/ticket/751.
        self.bus.log('Waiting for child threads to terminate...')
        for t in threading.enumerate():
            if t == threading.currentThread() or not t.isAlive():
                continue

            # Note that any dummy (external) threads are always daemonic.
            if t.daemon or isinstance(t, threading._MainThread):
                continue

            self.bus.log('Waiting for thread %s.' % t.getName())
            t.join()
    EXIT.priority = 100


class Execv(plugins.SimplePlugin):

    # Here I save the value of os.getcwd(), which, if I am imported early enough,
    # will be the directory from which the startup script was run.  This is needed
    # by _do_execv(), to change back to the original directory before execv()ing a
    # new process.  This is a defense against the application having changed the
    # current working directory (which could make sys.executable "not found" if
    # sys.executable is a relative-path, and/or cause other problems).
    _startup_cwd = os.getcwd()

    max_cloexec_files = max_files

    def execv(self):
        """Re-execute the current process.

        This must be called from the main thread on certain platforms (OS X)
        which don't allow execv to be called in a child thread very well.
        """
        args = sys.argv[:]
        self.bus.log('Re-spawning %s' % ' '.join(args))

        if sys.platform[:4] == 'java':
            from _systemrestart import SystemRestart
            raise SystemRestart
        else:
            args.insert(0, sys.executable)
            if sys.platform == 'win32':
                args = ['"%s"' % arg for arg in args]

            os.chdir(self._startup_cwd)
            if self.max_cloexec_files:
                self._set_cloexec()
            os.execv(sys.executable, args)
    EXITED = execv
    EXITED.priority = 100

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
