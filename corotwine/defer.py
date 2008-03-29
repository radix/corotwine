"""
corotwine.defer: Greenlet integration with Twisted Deferreds.
"""

from corotwine.protocol import MAIN

from twisted.python.failure import Failure
from twisted.python.util import mergeFunctionMetadata
from twisted.internet.defer import Deferred

from py.magic import greenlet


def blockOn(d):
    """
    Sblock on a Deferred.
    
    @return: The result of the Deferred.
    @raise: The exception that the Deferred was fired with.
    """
    current = greenlet.getcurrent()
    synchronous = []
    def cb(result):
        if greenlet.getcurrent() is current:
            synchronous.append(result)
        else: # Oh crap, this else is untested!
            current.switch(result)
    def eb(failure):
        if greenlet.getcurrent() is current:
            synchronous.append(failure)
        else: # Oh crap, this else is untested!
            failure.throwExceptionIntoGenerator(current)
    d.addCallbacks(cb, eb)
    if synchronous:
        if isinstance(synchronous[0], Failure):
            synchronous[0].raiseException()
        return synchronous[0]
    return MAIN.switch()

from twisted.internet.defer import succeed

def deferredGreenlet(gfunction):
    """
    Convert a function that will use greenlet to do context switching to one
    that returns a Deferred.

    This is a helper for writing functions to be used with frameworks which
    expect Deferreds to be returned.
    """
    # We need to know when gfunction is complete, i.e., when it actually
    # returns from its python frame.  There's no way to get a callback when
    # a greenlet "finishes" -- don't forget that the return of .switch() does
    # not mean the greenlet is done, just that someone's switched back to us.
    # So we create an intermediary function to run as the top-level greenlet
    # function.  It calls gfunction and fires the deferred with the result.
    def inner(*args, **kwargs):
        d = Deferred()
        def intermediateGreenletFunction():
            try:
                d.callback(gfunction(*args, **kwargs))
            except:
                d.errback()
        greenlet(intermediateGreenletFunction).switch()
        return d
    return mergeFunctionMetadata(gfunction, inner)


