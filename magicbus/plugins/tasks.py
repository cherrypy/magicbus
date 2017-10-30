"""Repeating tasks and monitors for a Bus."""

import os
import re
import sys
import time
import threading

from magicbus.plugins import SimplePlugin
from magicbus.compat import get_thread_ident, TimerClass

# _module__file__base is used by Autoreload to make
# absolute any filenames retrieved from sys.modules which are not
# already absolute paths.  This is to work around Python's quirk
# of importing the startup script and using a relative filename
# for it in sys.modules.
#
# Autoreload examines sys.modules afresh every time it runs. If an application
# changes the current directory by executing os.chdir(), then the next time
# Autoreload runs, it will not be able to find any filenames which are
# not absolute paths, because the current directory is not the same as when the
# module was first imported.  Autoreload will then wrongly conclude the file
# has "changed", and initiate the shutdown/re-exec sequence.
# See ticket #917.
# For this workaround to have a decent probability of success, this module
# needs to be imported as early as possible, before the app has much chance
# to change the working directory.
_module__file__base = os.getcwd()


class PerpetualTimer(TimerClass):
    """A responsive subclass of threading.Timer whose run() method repeats.

    Use this timer only when you really need a very interruptible timer;
    this checks its 'finished' condition up to 20 times a second, which can
    result in pretty high CPU usage.
    """

    def run(self):
        while True:
            self.finished.wait(self.interval)
            if self.finished.isSet():
                return
            try:
                self.function(*self.args, **self.kwargs)
            except Exception:
                self.bus.log('Error in perpetual timer thread function %r.' %
                             self.function, level=40, traceback=True)
                # Quit on first error to avoid massive logs.
                raise


class BackgroundTask(threading.Thread):
    """A subclass of threading.Thread whose run() method repeats.

    Use this class for most repeating tasks. It uses time.sleep() to wait
    for each interval, which isn't very responsive; that is, even if you call
    self.cancel(), you'll have to wait until the sleep() call finishes before
    the thread stops. To compensate, it defaults to being daemonic, which means
    it won't delay stopping the whole process.
    """

    def __init__(self, interval, function, args=[], kwargs={}, bus=None):
        threading.Thread.__init__(self)
        self.interval = interval
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.running = False
        self.bus = bus

    def cancel(self):
        self.running = False

    def run(self):
        self.running = True
        while self.running:
            # Sleep. Split up so we respond to cancel within one second.
            wholesecs, fracsecs = divmod(self.interval, 1)
            for s in range(int(wholesecs)):
                time.sleep(1)
                if not self.running:
                    return
            if fracsecs:
                time.sleep(fracsecs)
                if not self.running:
                    return

            try:
                self.function(*self.args, **self.kwargs)
            except Exception:
                if self.bus:
                    self.bus.log('Error in background task thread function %r.'
                                 % self.function, level=40, traceback=True)
                # Quit on first error to avoid massive logs.
                raise

    def _set_daemon(self):
        return True


class Monitor(SimplePlugin):
    """WSPBus listener to periodically run a callback in its own thread."""

    callback = None
    """The function to call at intervals."""

    frequency = 60
    """The time in seconds between callback runs."""

    thread = None
    """A :class:`BackgroundTask<magicbus.plugins.tasks.BackgroundTask>` thread.
    """

    def __init__(self, bus, callback, frequency=60, name=None):
        SimplePlugin.__init__(self, bus)
        self.callback = callback
        self.frequency = frequency
        self.thread = None
        self.name = name

    def START(self):
        """Start our callback in its own background thread."""
        if self.frequency > 0:
            threadname = self.name or self.__class__.__name__
            if self.thread is None:
                self.thread = BackgroundTask(self.frequency, self.callback,
                                             bus=self.bus)
                self.thread.setName(threadname)
                self.thread.start()
                self.bus.log('Started monitor thread %r.' % threadname)
            else:
                self.bus.log('Monitor thread %r already started.' % threadname)
    START.priority = 70

    def STOP(self):
        """Stop our callback's background task thread."""
        if self.thread is None:
            self.bus.log('No thread running for %s.' %
                         self.name or self.__class__.__name__)
        else:
            if self.thread is not threading.currentThread():
                name = self.thread.getName()
                self.thread.cancel()
                if not self.thread.daemon:
                    self.bus.log('Joining %r' % name)
                    self.thread.join()
                self.bus.log('Stopped thread %r.' % name)
            self.thread = None


class Autoreloader(Monitor):
    """Monitor which re-executes the process when files change.

    This :ref:`plugin<plugins>` restarts the process (via :func:`os.execv`)
    if any of the files it monitors change (or is deleted). By default, the
    autoreloader monitors all imported modules; you can add to the
    set by adding to ``autoreload.files``::

        bus.autoreload.files.add(myFile)

    If there are imported files you do *not* wish to monitor, you can adjust
    the ``match`` attribute, a regular expression. For example, to stop
    monitoring the bus itself::

        bus.autoreload.match = r'^(?!magicbus).+'

    Like all :class:`Monitor<magicbus.plugins.tasks.Monitor>` plugins,
    the autoreload plugin takes a ``frequency`` argument. The default is
    1 second; that is, the autoreloader will examine files once each second.
    """

    files = None
    """The set of files to poll for modifications."""

    frequency = 1
    """The interval in seconds at which to poll for modified files."""

    match = '.*'
    """A regular expression by which to match filenames."""

    def __init__(self, bus, frequency=1, match='.*'):
        self.mtimes = {}
        self.files = set()
        self.match = match
        Monitor.__init__(self, bus, self.run, frequency)

    def START(self):
        """Start our own background task thread for self.run."""
        if self.thread is None:
            self.mtimes = {}
        Monitor.START(self)
    START.priority = 70

    def sysfiles(self):
        """Return a Set of sys.modules filenames to monitor."""
        files = set()
        for k, m in list(sys.modules.items()):
            if re.match(self.match, k):
                if (
                    hasattr(m, '__loader__') and
                    hasattr(m.__loader__, 'archive')
                ):
                    f = m.__loader__.archive
                else:
                    f = getattr(m, '__file__', None)
                    if f is not None and not os.path.isabs(f):
                        # ensure absolute paths so a os.chdir() in the app
                        # doesn't break me
                        f = os.path.normpath(
                            os.path.join(_module__file__base, f))
                files.add(f)
        return files

    def run(self):
        """Reload the process if registered files have been modified."""
        for filename in self.sysfiles() | self.files:
            if filename:
                if filename.endswith('.pyc'):
                    filename = filename[:-1]

                oldtime = self.mtimes.get(filename, 0)
                if oldtime is None:
                    # Module with no .py file. Skip it.
                    continue

                try:
                    mtime = os.stat(filename).st_mtime
                except OSError:
                    # Either a module with no .py file, or it's been deleted.
                    mtime = None

                if filename not in self.mtimes:
                    # If a module has no .py file, this will be None.
                    self.mtimes[filename] = mtime
                else:
                    if mtime is None or mtime > oldtime:
                        # The file has been deleted or modified.
                        self.bus.log('Restarting because %s changed.' %
                                     filename)
                        self.thread.cancel()
                        self.bus.log('Stopped thread %r.' %
                                     self.thread.getName())
                        self.bus.restart()
                        return


class ThreadManager(SimplePlugin):
    """Manager for HTTP request threads.

    If you have control over thread creation and destruction, publish to
    the 'acquire_thread' and 'release_thread' channels (for each thread).
    This will register/unregister the current thread and publish to
    'start_thread' and 'stop_thread' listeners in the bus as needed.

    If threads are created and destroyed by code you do not control
    (e.g., Apache), then, at the beginning of every HTTP request,
    publish to 'acquire_thread' only. You should not publish to
    'release_thread' in this case, since you do not know whether
    the thread will be re-used or not. The bus will call
    'stop_thread' listeners for you when it stops.
    """

    threads = None
    """A map of {thread ident: index number} pairs."""

    def __init__(self, bus):
        self.threads = {}
        SimplePlugin.__init__(self, bus)
        self.bus.listeners.setdefault('acquire_thread', set())
        self.bus.listeners.setdefault('start_thread', set())
        self.bus.listeners.setdefault('release_thread', set())
        self.bus.listeners.setdefault('stop_thread', set())

    def acquire_thread(self):
        """Run 'start_thread' listeners for the current thread.

        If the current thread has already been seen, any 'start_thread'
        listeners will not be run again.
        """
        thread_ident = get_thread_ident()
        if thread_ident not in self.threads:
            # We can't just use get_ident as the thread ID
            # because some platforms reuse thread ID's.
            i = len(self.threads) + 1
            self.threads[thread_ident] = i
            self.bus.publish('start_thread', i)

    def release_thread(self):
        """Release the current thread and run 'stop_thread' listeners."""
        thread_ident = get_thread_ident()
        i = self.threads.pop(thread_ident, None)
        if i is not None:
            self.bus.publish('stop_thread', i)

    def STOP(self):
        """Release all threads and run all 'stop_thread' listeners."""
        for thread_ident, i in self.threads.items():
            self.bus.publish('stop_thread', i)
        self.threads.clear()
