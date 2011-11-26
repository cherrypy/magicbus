"""Regression test suite for magicbus.

Run 'nosetests -s test/' to exercise all tests.
"""

def assertEqual(x, y, msg=None):
    if not x == y:
        raise AssertionError(msg or "%r != %r" % (x, y))

