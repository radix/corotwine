"""
Corotwine, a coroutine-based API for Twisted.
"""

# Expose an alias for the greenlet package in use
try:
    from py.magic import greenlet
except ImportError:
    from greenlet import greenlet
