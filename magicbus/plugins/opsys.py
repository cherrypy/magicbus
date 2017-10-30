"""Operating system interaction for a Bus."""

import os
import sys
import threading
import time

from magicbus.plugins import SimplePlugin
from magicbus.compat import basestring, ntob


try:
    import pwd
    import grp
except ImportError:
    pwd, grp = None, None


class DropPrivileges(SimplePlugin):
    """Drop privileges. uid/gid arguments not available on Windows.

    Special thanks to Gavin Baker: http://antonym.org/node/100.
    """

    def __init__(self, bus, umask=None, uid=None, gid=None):
        SimplePlugin.__init__(self, bus)
        self.finalized = False
        self.uid = uid
        self.gid = gid
        self.umask = umask

    @property
    def uid(self):
        """The uid under which to run. Availability: Unix."""
        return self._uid

    @uid.setter
    def uid(self, val):
        if val is not None:
            if pwd is None:
                self.bus.log('pwd module not available; ignoring uid.',
                             level=30)
                val = None
            elif isinstance(val, basestring):
                val = pwd.getpwnam(val)[2]
        self._uid = val

    @property
    def gid(self):
        """The gid under which to run. Availability: Unix."""
        return self._gid

    @gid.setter
    def gid(self, val):
        if val is not None:
            if grp is None:
                self.bus.log('grp module not available; ignoring gid.',
                             level=30)
                val = None
            elif isinstance(val, basestring):
                val = grp.getgrnam(val)[2]
        self._gid = val

    @property
    def umask(self):
        """The default permission mode for newly created files and directories.

        Usually expressed in octal format, for example, ``0644``.
        Availability: Unix, Windows.
        """
        return self._umask

    @umask.setter
    def umask(self, val):
        if val is not None:
            try:
                os.umask
            except AttributeError:
                self.bus.log('umask function not available; ignoring umask.',
                             level=30)
                val = None
        self._umask = val

    def START(self):
        # uid/gid
        def current_ids():
            """Return the current (uid, gid) if available."""
            name, group = None, None
            if pwd:
                name = pwd.getpwuid(os.getuid())[0]
            if grp:
                group = grp.getgrgid(os.getgid())[0]
            return name, group

        if self.finalized:
            if not (self.uid is None and self.gid is None):
                self.bus.log('Already running as uid: %r gid: %r' %
                             current_ids())
        else:
            if self.uid is None and self.gid is None:
                if pwd or grp:
                    self.bus.log('uid/gid not set', level=30)
            else:
                self.bus.log('Started as uid: %r gid: %r' % current_ids())
                if self.gid is not None:
                    os.setgid(self.gid)
                    os.setgroups([])
                if self.uid is not None:
                    os.setuid(self.uid)
                self.bus.log('Running as uid: %r gid: %r' % current_ids())

        # umask
        if self.finalized:
            if self.umask is not None:
                self.bus.log('umask already set to: %03o' % self.umask)
        else:
            if self.umask is None:
                self.bus.log('umask not set', level=30)
            else:
                old_umask = os.umask(self.umask)
                self.bus.log('umask old: %03o, new: %03o' %
                             (old_umask, self.umask))

        self.finalized = True
    # This is slightly higher than the priority for server.START
    # in order to facilitate the most common use: starting on a low
    # port (which requires root) and then dropping to another user.
    START.priority = 77


class Daemonizer(SimplePlugin):
    """Daemonize the running script.

    Use this with a Bus via::

        Daemonizer(bus).subscribe()

    When this component finishes, the process is completely decoupled from
    the parent environment. Please note that when this component is used,
    the return code from the parent process will still be 0 if a startup
    error occurs in the forked children. Errors in the initial daemonizing
    process still return proper exit codes. Therefore, if you use this
    plugin to daemonize, don't use the return code as an accurate indicator
    of whether the process fully started. In fact, that return code only
    indicates if the process succesfully finished the first fork.
    """

    def __init__(self, bus, stdin='/dev/null', stdout='/dev/null',
                 stderr='/dev/null'):
        SimplePlugin.__init__(self, bus)
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.finalized = False

    def ENTER(self):
        if self.finalized:
            self.bus.log('Already daemonized.')

        # forking has issues with threads:
        # http://www.opengroup.org/onlinepubs/000095399/functions/fork.html
        # "The general problem with making fork() work in a multi-threaded
        #  world is what to do with all of the threads..."
        # So we check for active threads:
        if threading.activeCount() != 1:
            self.bus.log('There are %r active threads. '
                         'Daemonizing now may cause strange failures.' %
                         threading.enumerate(), level=30)

        # See http://www.erlenstar.demon.co.uk/unix/faq_2.html#SEC16
        # (or http://www.faqs.org/faqs/unix-faq/programmer/faq/ section 1.7)
        # and http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/66012

        # Finish up with the current stdout/stderr
        sys.stdout.flush()
        sys.stderr.flush()

        # Do first fork.
        try:
            pid = os.fork()
            if pid == 0:
                # This is the child process. Continue.
                pass
            else:
                # This is the first parent. Exit, now that we've forked.
                self.bus.log('Forking once.')
                os._exit(0)
        except OSError:
            # Python raises OSError rather than returning negative numbers.
            exc = sys.exc_info()[1]
            sys.exit('%s: fork #1 failed: (%d) %s\n'
                     % (sys.argv[0], exc.errno, exc.strerror))

        os.setsid()

        # Do second fork
        try:
            pid = os.fork()
            if pid > 0:
                self.bus.log('Forking twice.')
                os._exit(0)  # Exit second parent
        except OSError:
            exc = sys.exc_info()[1]
            sys.exit('%s: fork #2 failed: (%d) %s\n'
                     % (sys.argv[0], exc.errno, exc.strerror))

        os.chdir('/')
        os.umask(0)

        si = open(self.stdin, 'r')
        so = open(self.stdout, 'a+')
        se = open(self.stderr, 'a+')

        # os.dup2(fd, fd2) will close fd2 if necessary,
        # so we don't explicitly close stdin/out/err.
        # See http://docs.python.org/lib/os-fd-ops.html
        os.dup2(si.fileno(), sys.stdin.fileno())
        os.dup2(so.fileno(), sys.stdout.fileno())
        os.dup2(se.fileno(), sys.stderr.fileno())

        self.bus.log('Daemonized to PID: %s' % os.getpid())
        self.finalized = True
    ENTER.priority = 65


class PIDFile(SimplePlugin):
    """Maintain a PID file via a WSPBus."""

    def __init__(self, bus, pidfile):
        SimplePlugin.__init__(self, bus)
        self.pidfile = pidfile
        self.finalized = False

    def ENTER(self):
        pid = os.getpid()
        if self.finalized:
            self.bus.log('PID %r already written to %r.' % (pid, self.pidfile))
        else:
            open(self.pidfile, 'wb').write(ntob('%s' % pid, 'utf8'))
            self.bus.log('PID %r written to %r.' % (pid, self.pidfile))
            self.finalized = True
    ENTER.priority = 70

    def EXIT(self):
        try:
            os.remove(self.pidfile)
            self.bus.log('PID file removed: %r.' % self.pidfile)
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            pass

    def wait(self, timeout=None, poll_interval=0.1):
        """Return the PID when the file exists, or None when timeout expires.
        """
        starttime = time.time()
        while timeout is None or time.time() - starttime <= timeout:
            if os.path.exists(self.pidfile):
                return int(open(self.pidfile, 'rb').read())
            time.sleep(poll_interval)

    def join(self, timeout=None, poll_interval=0.1):
        """Return when the PID file does not exist, or the timeout expires."""
        starttime = time.time()
        while timeout is None or time.time() - starttime <= timeout:
            if not os.path.exists(self.pidfile):
                return
            time.sleep(poll_interval)
