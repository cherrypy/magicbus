import unittest

from magicbus.base import Graph


class GraphTests(unittest.TestCase):

    maxDiff = None

    #                                                       EXIT_ERROR
    #                                                           |
    #                                                           V
    #                        START -----------> EXIT ------> EXITED
    #                      /   |    A    /        A
    #                     V    |     \  /         |
    # START_ERROR        RUN   |    IDLE     STOP_ERROR
    #      |              \    |     A
    #      |               V   V    /
    #      +----------------> STOP
    transitions = {
        'START': ('RUN', 'STOP', 'EXIT'),
        'RUN': 'STOP',
        'START_ERROR': 'STOP',
        'STOP': 'IDLE',
        'IDLE': ('START', 'EXIT'),
        'STOP_ERROR': 'EXIT',
        'EXIT': 'EXITED',
        'EXIT_ERROR': 'EXITED',
    }

    next = {
        ('EXIT', 'EXITED'): 'EXITED',
        ('EXIT_ERROR', 'EXITED'): 'EXITED',
        ('IDLE', 'EXITED'): 'EXIT',
        ('IDLE', 'EXIT'): 'EXIT',
        ('IDLE', 'RUN'): 'START',
        ('IDLE', 'START'): 'START',
        ('IDLE', 'STOP'): 'START',
        ('RUN', 'EXITED'): 'STOP',
        ('RUN', 'EXIT'): 'STOP',
        ('RUN', 'IDLE'): 'STOP',
        ('RUN', 'START'): 'STOP',
        ('RUN', 'STOP'): 'STOP',
        ('START', 'EXITED'): 'EXIT',
        ('START', 'EXIT'): 'EXIT',
        ('START', 'IDLE'): 'STOP',
        ('START', 'RUN'): 'RUN',
        ('START', 'STOP'): 'STOP',
        ('START_ERROR', 'EXITED'): 'STOP',
        ('START_ERROR', 'EXIT'): 'STOP',
        ('START_ERROR', 'IDLE'): 'STOP',
        ('START_ERROR', 'RUN'): 'STOP',
        ('START_ERROR', 'START'): 'STOP',
        ('START_ERROR', 'STOP'): 'STOP',
        ('STOP', 'EXITED'): 'IDLE',
        ('STOP', 'EXIT'): 'IDLE',
        ('STOP', 'IDLE'): 'IDLE',
        ('STOP', 'RUN'): 'IDLE',
        ('STOP', 'START'): 'IDLE',
        ('STOP_ERROR', 'EXITED'): 'EXIT',
        ('STOP_ERROR', 'EXIT'): 'EXIT',
    }

    states = set(['START', 'RUN', 'STOP', 'IDLE', 'EXIT', 'EXITED',
                 'START_ERROR', 'STOP_ERROR', 'EXIT_ERROR'])

    def test_shortest_path(self):
        g = Graph.from_edges(self.transitions)
        self.assertEqual(g, self.next)

    def test_states(self):
        g = Graph(self.next)
        self.assertEqual(g.states, self.states)
