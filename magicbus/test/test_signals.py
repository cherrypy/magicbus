import errno
import os
thismodule = os.path.abspath(__file__)
import sys
import time

import pytest

from magicbus import bus
from magicbus.plugins import loggers, opsys, signalhandler
from magicbus.test import Process


@pytest.fixture
def kill():
    try:
        return os.kill
    except AttributeError:
        pytest.skip('no os.kill')


@pytest.fixture
def signal():
    return pytest.importorskip('signal')


@pytest.fixture
def SIGHUP(signal):
    try:
        return signal.SIGHUP
    except AttributeError:
        pytest.skip('no SIGHUP')


@pytest.fixture
def SIGTERM(signal):
    try:
        return signal.SIGTERM
    except AttributeError:
        pytest.skip('no SIGTERM')


@pytest.fixture
def logfile(request):
    # Ref: https://stackoverflow.com/a/34732269/595220
    test_name = request.node.originalname
    path = os.path.join(
        os.path.dirname(thismodule),
        '.'.join((__name__ or 'test_signals', test_name, 'log')),
    )

    try:
        os.remove(path)
    except OSError as os_err:
        if os_err.errno != errno.ENOENT:
            raise
    finally:
        return path


@pytest.fixture
def pidfile(tmp_path):
    pid_file_path = tmp_path / (__name__ or 'test_signals' + '.pid')
    return opsys.PIDFile(bus, str(pid_file_path))


@pytest.fixture
def tty_process_pid(pidfile, logfile):
    pid_file_path = pidfile.pidfile
    Process([
        sys.executable, thismodule,
        'tty', pid_file_path, logfile,
    ]).start()
    pid = pidfile.wait()
    return pid


@pytest.fixture
def daemon_process_pid(pidfile, logfile):
    pid_file_path = pidfile.pidfile
    Process([
        sys.executable, thismodule,
        'daemonize', pid_file_path, logfile,
    ]).start()
    pid = pidfile.wait()
    return pid


def test_SIGHUP_tty(pidfile, tty_process_pid, kill, SIGHUP):
    # When not daemonized, SIGHUP should exit the process.
    kill(tty_process_pid, SIGHUP)
    pidfile.join()


@pytest.mark.skipif(os.name != 'posix', reason='only supported on POSIX')
def test_SIGHUP_daemonized(pidfile, daemon_process_pid, kill, SIGHUP, SIGTERM):
    # When daemonized, SIGHUP should restart the server.
    kill(daemon_process_pid, SIGHUP)

    # Give the server some time to restart
    time.sleep(1)
    for _ in range(6):
        new_pid = pidfile.wait(5)
        if new_pid != daemon_process_pid:
            break
        time.sleep(5)
    assert new_pid is not None
    assert new_pid != daemon_process_pid
    kill(new_pid, SIGTERM)
    pidfile.join()


@pytest.mark.xfail(
    sys.platform == 'win32',
    reason='The non-daemonized process cannot detect the TTY on Windows for some reason',
    run=False,
)
def test_SIGTERM_tty(pidfile, tty_process_pid, kill, SIGTERM):
    # SIGTERM should shut down the server whether daemonized or not.

    kill(tty_process_pid, SIGTERM)
    pidfile.join()


@pytest.mark.skipif(os.name != 'posix', reason='only supported on POSIX')
def test_SIGTERM_daemonized(pidfile, daemon_process_pid, kill, SIGTERM):
    # SIGTERM should shut down the server whether daemonized or not.
    kill(daemon_process_pid, SIGTERM)
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
