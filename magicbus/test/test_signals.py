import os
thismodule = os.path.abspath(__file__)
import sys
import time

import pytest

from magicbus import bus
from magicbus.plugins import loggers, opsys, signalhandler
from magicbus.test import Process

logfile = os.path.join(os.path.dirname(thismodule), 'test_signals.log')
loggers.FileLogger(bus, logfile).subscribe()
pidfile = opsys.PIDFile(bus, os.path.join(thismodule + '.pid'))


def test_SIGHUP_tty():
    # When not daemonized, SIGHUP should exit the process.
    try:
        from signal import SIGHUP
    except ImportError:
        return 'skipped (no SIGHUP)'

    try:
        from os import kill
    except ImportError:
        return 'skipped (no os.kill)'

    p = Process([sys.executable, thismodule, 'tty'])
    p.start()
    pid = pidfile.wait()
    kill(pid, SIGHUP)
    pidfile.join()


def test_SIGHUP_daemonized():
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

    os.remove(logfile)

    p = Process([sys.executable, thismodule, 'daemonize'])
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
def test_SIGTERM_tty():
    # SIGTERM should shut down the server whether daemonized or not.
    try:
        from signal import SIGTERM
    except ImportError:
        return 'skipped (no SIGTERM)'

    try:
        from os import kill
    except ImportError:
        return 'skipped (no os.kill)'

    # Spawn a normal, undaemonized process.
    p = Process([sys.executable, thismodule, 'tty'])
    p.start()
    pid = pidfile.wait()
    kill(pid, SIGTERM)
    pidfile.join()


def test_SIGTERM_daemonized():
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

    # Spawn a daemonized process and test again.
    p = Process([sys.executable, thismodule, 'daemonize'])
    p.start()
    pid = pidfile.wait()
    kill(pid, SIGTERM)
    pidfile.join()


if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'daemonize':
        opsys.Daemonizer(bus).subscribe()
    pidfile.subscribe()
    signalhandler.SignalHandler(bus).subscribe()
    bus.transition('RUN')
    bus.block()
