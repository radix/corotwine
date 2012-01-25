"""
Time manipulation for greenlets.
"""

from corotwine import greenlet
from corotwine.protocol import MAIN

def wait(seconds, clock=None):
    """
    Wait a number of seconds before returning control to the calling greenlet.

    @param seconds: Number of seconds to wait.
    @type seconds: C{int}
    @param clock: The clock with which to schedule the return to this greenlet.
    @type clock: L{twisted.internet.interfaces.IReactorTime} provider.
    """
    if clock is None:
        from twisted.internet import reactor as clock
    thisGreenlet = greenlet.getcurrent()
    clock.callLater(seconds, thisGreenlet.switch)
    return MAIN.switch()
