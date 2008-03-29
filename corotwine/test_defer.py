"""
Tests for L{corotwine.defer}.
"""
from py.magic import greenlet

from corotwine.defer import blockOn, deferredGreenlet
from corotwine.clock import wait

from twisted.internet.defer import Deferred, succeed, fail
from twisted.internet.task import Clock
from twisted.python.failure import Failure
from twisted.trial.unittest import TestCase


class BlockOnTests(TestCase):
    """
    Tests for L{blockOn}.
    """

    def test_simpleBlock(self):
        """
        A greenlet which calls L{blockOn} will be resumed when the Deferred
        passed has fired.
        """
        events = []
        deferred = Deferred()
        def greeny():
            events.append("waiting")
            events.append(blockOn(deferred))
        greenlet(greeny).switch()
        self.assertEquals(events, ["waiting"])
        deferred.callback("hey")
        self.assertEquals(events, ["waiting", "hey"])


    def test_errback(self):
        """
        L{blockOn} will raise an exception when the Deferred fires with an
        error.
        """
        events = []
        deferred = Deferred()
        def catcher():
            events.append("waiting")
            try:
                blockOn(deferred)
            except Exception, e:
                events.append(e)
        greenlet(catcher).switch()
        self.assertEquals(events, ["waiting"])
        e = ZeroDivisionError("Yeah whatever")
        deferred.errback(e)
        self.assertEquals(events, ["waiting", e])


    def test_alreadyHasResult(self):
        """
        Passing an already-fired Deferred to L{blockOn} will immediately return
        that Deferred's result.
        """
        events = []
        deferred = succeed("hey")
        def greeny():
            events.append("waiting")
            events.append(blockOn(deferred))
        greenlet(greeny).switch()
        self.assertEquals(events, ["waiting", "hey"])


    def test_alreadyHasFailure(self):
        """
        Passing an already-failed Deferred to L{blockOn} will immediately raise
        an exception.
        """
        events = []
        e = ZeroDivisionError("whatever")
        deferred = fail(e)
        def greeny():
            events.append("waiting")
            try:
                blockOn(deferred)
            except Exception, e:
                events.append(e)
        greenlet(greeny).switch()
        self.assertEquals(events, ["waiting", e])


class DeferredGreenletTests(TestCase):
    """
    Tests for L{deferredGreenlet}.
    """

    def test_metadata(self):
        """
        The metadata of a L{deferredGreenlet}-wrapped function is the same as
        the original function.
        """
        def whatACoolName():
            """foo"""
            pass
        whatACoolName.attr = 3
        wrapped = deferredGreenlet(whatACoolName)
        self.assertEquals(wrapped.__name__, "whatACoolName")
        self.assertEquals(wrapped.__doc__, "foo")
        self.assertEquals(wrapped.attr, 3)
        self.assertEquals(wrapped.__module__, __name__)


    def test_returnSynchronousDeferred(self):
        """
        If the greenlet does not do any switching, the Deferred returned will
        have already fired.
        """
        @deferredGreenlet
        def greeny():
            return 1
        d = greeny()
        self.assertEquals(self.synchResult(d), 1)


    def synchResult(self, d):
        result = []
        d.addBoth(result.append)
        if isinstance(result[0], Failure):
            result[0].raiseException()
        return result[0]


    def test_returnAsynchronousDeferred(self):
        """
        If the greenlet does switch, the Deferred will fire only when the
        greenlet has returned.
        """
        clock = Clock()
        events = []
        @deferredGreenlet
        def waity():
            events.append("prewait")
            wait(3, clock)
        result = []
        d = waity()
        d.addCallback(result.append)
        # Make sure the deferred has *not* fired yet...
        self.assertEquals(result, [])
        # But the greenlet *has* been started
        self.assertEquals(events, ["prewait"])

        clock.advance(3)
        self.assertEquals(result, [None])


    def test_failingDeferred(self):
        """
        If the greenlet raises an exception, it will me translated to a failing
        Deferred.
        """
        @deferredGreenlet
        def buggy():
            1/0
        d = buggy()
        self.assertFailure(d, ZeroDivisionError)
        return d


    def test_arguments(self):
        """
        The decorated function can take arbitrary arguments.
        """
        @deferredGreenlet
        def argumentative(foo, x=3, y=None):
            return foo, x, y
        d = argumentative(1, y="val")
        self.assertEquals(self.synchResult(d), (1, 3, "val"))


    def test_instanceMethod(self):
        """
        The decorated function can be an instance method.
        """
        class Whatever(object):
            @deferredGreenlet
            def instancey(self, a, b=3):
                return self, a, b
        whatever = Whatever()
        d = whatever.instancey(1)
        self.assertEquals(self.synchResult(d), (whatever, 1, 3))
