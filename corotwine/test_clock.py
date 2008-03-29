"""
Tests for L{corotwine.clock}.
"""
from twisted.trial.unittest import TestCase
from twisted.internet.task import Clock

from py.magic import greenlet

from corotwine.clock import wait


class TimeTest(TestCase):
    """
    Tests for L{corotwine.time}.
    """
    def test_wait(self):
        """
        L{wait} returns when an amount of time has been passed, allowing the
        reactor to run in the meantime.
        """
        clock = Clock()
        events = []
        def doit():
            events.append("waiting")
            wait(5, clock)
            events.append("done")
        g = greenlet(doit)
        g.switch()
        self.assertEquals(events, ["waiting"])
        clock.advance(5)
        self.assertEquals(events, ["waiting", "done"])
