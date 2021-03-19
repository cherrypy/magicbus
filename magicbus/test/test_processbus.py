from __future__ import print_function

import functools
import sys
import threading
import time

import pytest

from magicbus.base import Bus, ChannelFailures
from magicbus.process import ProcessBus


__metaclass__ = type


msg = 'Listener %d on channel %s: %s.'
print_to_stderr = functools.partial(print, file=sys.stderr)


class TestPublishSubscribe:

    def get_listener(self, channel, index):
        def listener(*args):
            self.responses.append(msg % (index, channel, args))
        return listener

    def test_builtin_channels(self):
        b = ProcessBus()
        listeners = [l for l in b.listeners
                     if l != 'log' and not l.endswith('_ERROR')]

        self.responses, expected = [], []

        for channel in listeners:
            if channel != 'log':
                for index, priority in enumerate([100, 50, 0, 51]):
                    b.subscribe(channel,
                                self.get_listener(channel, index), priority)

        try:
            for channel in listeners:
                if channel != 'log':
                    b.publish(channel)
                    expected.extend([msg % (i, channel, ()) for i in (2, 1, 3, 0)])

            assert self.responses == expected
        finally:
            # Exit so the atexit handler doesn't complain.
            b.transition('EXITED')

    def test_custom_channels(self):
        b = Bus()

        self.responses, expected = [], []

        custom_listeners = ('hugh', 'louis', 'dewey')
        for channel in custom_listeners:
            for index, priority in enumerate([None, 10, 60, 40]):
                b.subscribe(channel,
                            self.get_listener(channel, index), priority)

        for channel in custom_listeners:
            b.publish(channel, 'ah so')
            expected.extend([msg % (i, channel, ('ah so',))
                            for i in (1, 3, 0, 2)])
            b.publish(channel)
            expected.extend([msg % (i, channel, ()) for i in (1, 3, 0, 2)])

        assert self.responses == expected

    def test_listener_errors(self):
        b = Bus()

        self.responses, expected = [], []
        # FIXME: should this be bigger than 0 non-log channels?
        channels = [c for c in b.listeners if c != 'log']

        for channel in channels:
            b.subscribe(channel, self.get_listener(channel, 1))
            # This will break since the lambda takes no args.
            b.subscribe(channel, lambda: None, priority=20)

        for channel in channels:
            with pytest.raises(ChannelFailures):  # FIXME: add `match=`
                b.publish(channel, 123)
            expected.append(msg % (1, channel, (123,)))

        assert self.responses == expected


class TestBusMethod:

    def log(self, bus, level=10):
        self._log_entries = []
        self.level = level

        def logit(msg_, level):
            if level >= self.level:
                self._log_entries.append(msg_)
        bus.subscribe('log', logit)

        # NOTE: Also print to stderr so that pytest would
        # NOTE: dump it to screen on failure.
        bus.subscribe('log', print_to_stderr)

    def assertLog(self, entries):
        assert self._log_entries == entries

    def get_listener(self, channel, index):
        def listener(arg=None):
            self.responses.append(msg % (index, channel, arg))
        return listener

    def test_idle_to_run(self):
        b = ProcessBus()
        self.log(b, level=20)

        self.responses = []
        num = 3
        for index in range(num):
            b.subscribe('START', self.get_listener('START', index))

        b.transition('RUN')
        try:
            # The start method MUST call all 'start' listeners.
            assert (
                set(self.responses) ==
                set([msg % (i, 'START', None) for i in range(num)])
            )
            # The transition method MUST move the state to RUN
            # (or START_ERROR, if errors occur)
            assert b.state == 'RUN'

            # The start method MUST log its states.
            self.assertLog([
                'Bus state: ENTER',
                'Bus state: IDLE',
                'Bus state: START',
                'Bus state: RUN'
            ])
        finally:
            # Exit so the atexit handler doesn't complain.
            b.transition('EXITED')

    def test_run_to_idle(self):
        b = ProcessBus()
        b.transition('RUN')
        self.log(b, level=20)

        try:
            self.responses = []
            num = 3
            for index in range(num):
                b.subscribe('STOP', self.get_listener('STOP', index))

            b.transition('IDLE')

            # The idle transition MUST call all 'stop' listeners.
            assert (
                set(self.responses) ==
                set(msg % (i, 'STOP', None) for i in range(num))
            )
            # The idle method MUST move the state to IDLE
            assert b.state == 'IDLE'
            # The idle method MUST log its states.
            self.assertLog([
                'Bus state: STOP',
                'Bus state: IDLE'
            ])
        finally:
            # Exit so the atexit handler doesn't complain.
            b.transition('EXITED')

    def test_idle_to_exit(self):
        b = ProcessBus()
        self.log(b, level=20)

        self.responses = []
        num = 3
        for index in range(num):
            b.subscribe('EXIT', self.get_listener('EXIT', index))
            b.subscribe('EXITED', self.get_listener('EXITED', index))

        b.transition('EXITED')

        # The bus MUST call all 'EXIT' listeners,
        # and then all 'EXITED' listeners.
        assert (
            set(self.responses) ==
            set([msg % (i, 'EXIT', None) for i in range(num)] +
                [msg % (i, 'EXITED', None) for i in range(num)])
        )
        # The bus MUST move the state to EXITED
        assert b.state == 'EXITED'

        # The bus MUST log its states.
        self.assertLog([
            'Bus state: ENTER',
            'Bus state: IDLE',
            'Bus state: EXIT',
            'Waiting for child threads to terminate...',
            'Bus state: EXITED'
        ])

    @pytest.mark.xfail(
        reason=r"""Fails intermittently with
        Traceback (most recent call last):
        File "D:\a\magicbus\magicbus\magicbus\base.py",
             line 205, in _transition
        os.write(write_fd, b'1')
        OSError: [Errno 22] Invalid argument
        """,
        raises=AssertionError,
        strict=False,  # Because it's flaky
    )
    def test_wait(self):
        b = ProcessBus()
        self.log(b)

        def f(desired_state):
            time.sleep(0.2)
            b.transition(desired_state)

        for desired_state_, states_to_wait_for in [
            ('RUN', ['RUN']),
            ('IDLE', ['IDLE']),
            ('RUN', ['START', 'RUN']),
            ('EXITED', ['EXITED'])
        ]:
            threading.Thread(
                target=f, args=(desired_state_,),
                name='[test_wait] Transitioning to {state!s}'.
                format(state=desired_state_),
            ).start()
            b.wait(states_to_wait_for)

            actual_state = b.state
            # The wait method MUST wait for the given state(s).
            assert actual_state in states_to_wait_for, (
                'State {actual_state!r} not in {expected_states!r}.\n'
                'Log entries: {logs!r}'.
                format(
                    actual_state=actual_state,
                    expected_states=states_to_wait_for,
                    logs=self._log_entries,
                )
            )

        assert not any(
            t.is_alive() and t.name.startswith('[test_wait] ')
            for t in threading.enumerate()
        ), 'Post condition failed: some test threads are still alive'

    def test_block(self):
        b = ProcessBus()
        self.log(b)

        def f():
            time.sleep(0.2)
            b.transition('EXITED')

        def g():
            time.sleep(0.4)

        def main_listener():
            main_calls.append(1)
        main_calls = []
        b.subscribe('main', main_listener)

        f_thread = threading.Thread(target=f, name='f')
        f_thread.start()
        threading.Thread(target=g, name='g').start()

        spawned_threads = [
            t for t in threading.enumerate()
            if t.name in {'f', 'g'}
        ]
        assert all(t.is_alive() for t in spawned_threads)

        b.block()
        f_thread.join()

        # The block method MUST wait for the EXITED state.
        assert b.state == 'EXITED'
        # The block method MUST wait for ALL non-main, non-daemon threads to
        # finish.
        assert all(not t.is_alive() for t in spawned_threads)
        # The last message will mention an indeterminable thread name; ignore
        # it
        actual_state_changes = [
            entry for entry in self._log_entries
            if not entry.startswith(('Publishing', 'Waiting'))
        ]
        expected_state_change_order = [
            'Bus state: ENTER',
            'Bus state: IDLE',
            'Bus state: EXIT',
            'Bus state: EXITED',
        ]
        assert actual_state_changes == expected_state_change_order

        # While the bus was blocked, it should have published periodically
        # to the "main" channel.
        assert len(main_calls) > 0

    @pytest.mark.xfail(
        reason='Fails intermittently; https://tinyurl.com/ybwwu4gz',
        strict=False,  # Because it's flaky
    )
    def test_start_with_callback(self):
        b = ProcessBus()
        self.log(b)
        try:
            events = []

            def f(*args, **kwargs):
                events.append(('f', args, kwargs))

            def g():
                events.append('g')

            b.subscribe('RUN', g)
            b.start_with_callback(f, (1, 3, 5), {'foo': 'bar'})
            # Give wait() time to run f()
            time.sleep(0.2)

            # The callback method MUST wait for the STARTED state.
            assert b.state == 'RUN'
            # The callback method MUST run after all start methods.
            assert events == ['g', ('f', (1, 3, 5), {'foo': 'bar'})]
        finally:
            b.transition('EXITED')

    def test_log(self):
        b = Bus()
        self.log(b)
        self.assertLog([])

        # Try a normal message.
        expected = []
        for _msg in ["O mah darlin'"] * 3 + ['Clementiiiiiiiine']:
            b.log(_msg)
            expected.append(_msg)
            self.assertLog(expected)

        # Try an error message
        try:
            foo
        except NameError:
            b.log('You are lost and gone forever', traceback=True)
            lastmsg = self._log_entries[-1]
            assert 'Traceback' in lastmsg and 'NameError' in lastmsg, (
                'Last log message {msg!r} did not contain '
                'the expected traceback.'.format(msg=lastmsg)
            )
        else:
            pytest.fail('NameError was not raised as expected.')
