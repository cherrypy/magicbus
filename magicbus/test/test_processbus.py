import threading
import time
import unittest

from magicbus.base import Bus, ChannelFailures
from magicbus.process import ProcessBus


msg = 'Listener %d on channel %s: %s.'


class PublishSubscribeTests(unittest.TestCase):

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

            self.assertEqual(self.responses, expected)
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

        self.assertEqual(self.responses, expected)

    def test_listener_errors(self):
        b = Bus()

        self.responses, expected = [], []
        channels = [c for c in b.listeners if c != 'log']

        for channel in channels:
            b.subscribe(channel, self.get_listener(channel, 1))
            # This will break since the lambda takes no args.
            b.subscribe(channel, lambda: None, priority=20)

        for channel in channels:
            self.assertRaises(ChannelFailures, b.publish, channel, 123)
            expected.append(msg % (1, channel, (123,)))

        self.assertEqual(self.responses, expected)


class BusMethodTests(unittest.TestCase):

    maxDiff = None

    def log(self, bus, level=10):
        self._log_entries = []
        self.level = level

        def logit(msg_, level):
            if level >= self.level:
                self._log_entries.append(msg_)
        bus.subscribe('log', logit)

    def assertLog(self, entries):
        self.assertEqual(self._log_entries, entries)

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
            self.assertEqual(
                set(self.responses),
                set([msg % (i, 'START', None) for i in range(num)])
            )
            # The transition method MUST move the state to RUN
            # (or START_ERROR, if errors occur)
            self.assertEqual(b.state, 'RUN')

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
            self.assertEqual(
                set(self.responses),
                set(msg % (i, 'STOP', None) for i in range(num))
            )
            # The idle method MUST move the state to IDLE
            self.assertEqual(b.state, 'IDLE')
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
        self.assertEqual(
            set(self.responses),
            set([msg % (i, 'EXIT', None) for i in range(num)] +
                [msg % (i, 'EXITED', None) for i in range(num)])
        )
        # The bus MUST move the state to EXITED
        self.assertEqual(b.state, 'EXITED')

        # The bus MUST log its states.
        self.assertLog([
            'Bus state: ENTER',
            'Bus state: IDLE',
            'Bus state: EXIT',
            'Waiting for child threads to terminate...',
            'Bus state: EXITED'
        ])

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
            threading.Thread(target=f, args=(desired_state_,)).start()
            b.wait(states_to_wait_for)

            # The wait method MUST wait for the given state(s).
            if b.state not in states_to_wait_for:
                self.fail('State %r not in %r' % (b.state, states_to_wait_for))

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
        b.subscribe("main", main_listener)

        f_thread = threading.Thread(target=f, name='f')
        f_thread.start()
        threading.Thread(target=g, name='g').start()
        threads = [t for t in threading.enumerate() if not t.daemon]
        self.assertEqual(len(threads), 3)

        b.block()
        f_thread.join()

        # The block method MUST wait for the EXITED state.
        self.assertEqual(b.state, 'EXITED')
        # The block method MUST wait for ALL non-main, non-daemon threads to
        # finish.
        threads = [t for t in threading.enumerate() if not t.daemon]
        self.assertEqual(len(threads), 1)
        # The last message will mention an indeterminable thread name; ignore
        # it
        self.assertEqual(
            [entry for entry in self._log_entries
             if not entry.startswith('Publishing')
             and not entry.startswith('Waiting')],
            [
                'Bus state: ENTER',
                'Bus state: IDLE',
                'Bus state: EXIT',
                'Bus state: EXITED'
            ]
        )

        # While the bus was blocked, it should have published periodically
        # to the "main" channel.
        self.assertGreater(len(main_calls), 0)

    @unittest.skip("Fails intermittently; https://tinyurl.com/ybwwu4gz")
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
            self.assertEqual(b.state, 'RUN')
            # The callback method MUST run after all start methods.
            self.assertEqual(events, ['g', ('f', (1, 3, 5), {'foo': 'bar'})])
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
            if 'Traceback' not in lastmsg or 'NameError' not in lastmsg:
                self.fail('Last log message %r did not contain '
                          'the expected traceback.' % lastmsg)
        else:
            self.fail('NameError was not raised as expected.')


if __name__ == '__main__':
    unittest.main()
