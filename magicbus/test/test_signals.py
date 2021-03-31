import os
thismodule = os.path.abspath(__file__)
import sys
import time

import pytest

from magicbus import bus
from magicbus.plugins import loggers, opsys, signalhandler
from magicbus.test import Process


@pytest.fixture
def logfile(request):
    # Ref: https://stackoverflow.com/a/34732269/595220
    test_name = request.node.originalname
    return os.path.join(
        os.path.dirname(thismodule),
        '.'.join((__name__, test_name, 'log')),
    )


@pytest.fixture
def pidfile(tmp_path):
    pid_file_path = tmp_path / (__name__ + '.pid')
    return opsys.PIDFile(bus, str(pid_file_path))


def test_SIGHUP_tty(pidfile, logfile):
    # When not daemonized, SIGHUP should exit the process.
    try:
        from signal import SIGHUP
    except ImportError:
        return 'skipped (no SIGHUP)'

    try:
        from os import kill
    except ImportError:
        return 'skipped (no os.kill)'

    pid_file_path = pidfile.pidfile

    p = Process([sys.executable, thismodule, 'tty', pid_file_path, logfile])
    p.start()
    pid = pidfile.wait()
    kill(pid, SIGHUP)
    pidfile.join()


def test_SIGHUP_daemonized(pidfile, logfile):
    # When daemonized, SIGHUP should restart the server.
    try:
        from signal import SIGHUP, SIGTERM
    except ImportError:
        return 'skipped (no SIGHUP)'

    try:
        from os import kill
    except ImportError:
        return 'skipped (no os.kill)'

    if os.name not in ['posix']:
        return 'skipped (not on posix)'

    try:
        os.remove(logfile)
    except OSError as os_err:
        import errno
        if os_err.errno != errno.ENOENT:
            raise

    pid_file_path = pidfile.pidfile

    p = Process([sys.executable, thismodule, 'daemonize', pid_file_path, logfile])
    p.start()
    pid = pidfile.wait()
    kill(pid, SIGHUP)

    # Give the server some time to restart
    time.sleep(1)
    for _ in range(6):
        new_pid = pidfile.wait(5)
        if new_pid != pid:
            break
        time.sleep(5)
    assert new_pid is not None
    assert new_pid != pid
    kill(new_pid, SIGTERM)
    pidfile.join()


@pytest.mark.xfail(
    sys.platform == 'win32',
    reason='The non-daemonized process cannot detect the TTY on Windows for some reason',
    run=False,
)
def test_SIGTERM_tty(pidfile, logfile):
    # SIGTERM should shut down the server whether daemonized or not.
    try:
        from signal import SIGTERM
    except ImportError:
        return 'skipped (no SIGTERM)'

    try:
        from os import kill
    except ImportError:
        return 'skipped (no os.kill)'

    pid_file_path = pidfile.pidfile

    # Spawn a normal, undaemonized process.
    p = Process([sys.executable, thismodule, 'tty', pid_file_path, logfile])
    p.start()
    pid = pidfile.wait()
    kill(pid, SIGTERM)
    pidfile.join()


def test_SIGTERM_daemonized(pidfile, logfile):
    # SIGTERM should shut down the server whether daemonized or not.
    try:
        from signal import SIGTERM
    except ImportError:
        return 'skipped (no SIGTERM)'

    try:
        from os import kill
    except ImportError:
        return 'skipped (no os.kill)'

    if os.name not in ['posix']:
        return 'skipped (not on posix)'

    pid_file_path = pidfile.pidfile

    # Spawn a daemonized process and test again.
    p = Process([sys.executable, thismodule, 'daemonize', pid_file_path, logfile])
    p.start()
    pid = pidfile.wait()
    kill(pid, SIGTERM)
    pidfile.join()


if __name__ == '__main__':
    mode, pid_file_path, logfile = sys.argv[1:4]
    loggers.FileLogger(bus, logfile).subscribe()
    if mode == 'daemonize':
        opsys.Daemonizer(bus).subscribe()
    opsys.PIDFile(bus, pid_file_path).subscribe()
    signalhandler.SignalHandler(bus).subscribe()
    bus.transition('RUN')
    bus.block()
