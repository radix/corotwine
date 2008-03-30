"""
I/O support for greenlets on Twisted.

See L{corotwine.examples} for examples of using the API in this module.

This will start an echo server on port 1027.  To see what else can be done
with C{transport}, refer to L{GreenletTransport}.

By the way, I have a niggling suspicion that it's a really bad idea to use
C{transport} from multiple greenlets.
"""

from twisted.internet.defer import Deferred
from twisted.internet.protocol import Protocol, Factory, ClientFactory
from twisted.internet.error import ConnectionLost, ConnectionDone
from twisted.protocols.basic import LineReceiver

from py.magic import greenlet


MAIN = greenlet.getcurrent()

READING, WRITING = range(2)


__all__ = ["MAIN", "LineBuffer", "gListenTCP", "gConnectTCP"]


class LineBuffer(object):
    """
    A line-buffering wrapper for L{GreenletTransport}s (or any other object
    with C{read} and C{write} methods). Call L{readLine} to get the next line,
    call L{writeLine} to write a line.
    """
    def __init__(self, transport, delimiter="\r\n"):
        """
        @param transport: The transport from which to read bytes and to which
            to write them!
        @type transport: L{GreenletTransport}
        @param delimiter: The line delimiter to split lines on.
        @type delimiter: C{str}
        """
        self.delimiter = delimiter
        self.transport = transport
        self.receiver = LineReceiver()
        self.receiver.delimiter = delimiter
        self.lines = []
        self.receiver.lineReceived = self.lines.append

    def writeLine(self, data):
        """
        Write some data to the transport followed by the delimiter.
        """
        self.transport.write(data + self.delimiter)

    def readLine(self):
        """
        Return a line of data from the transport.
        """
        while not self.lines:
            self.receiver.dataReceived(self.transport.read())
        return self.lines.pop(0)

    def __iter__(self):
        """
        Yield the result of L{readLine} forever.
        """
        while True:
            yield self.readLine()



class GreenletTransport(object):
    """
    An object which represents a connection that greenlets can use.

    @ivar _transport: See L{__init__}.
    @ivar _protocol: See L{__init__}.
    @ivar _disconnected: None or a L{twisted.python.failure.Failure}. If set,
        I/O operations will raise the encapsulated error.
    @ivar _state: Indicates whether the greenlet hooked up to this transport
        is currently reading or writing. Can be C{READING} or C{WRITING}.
    @type _state: One of C{READING, WRITING}.
    """

    def __init__(self, transport, protocol):
        """
        @param transport: The real, underlying Twisted transport.
        @type transport: L{twisted.internet.interfaces.ITransport}
        @param protocol: The L{_GreenletProtocol}.
        @type protocol: L{_GreenletProtocol}
        """
        self._transport = transport
        self._disconnected = None
        self._state = None
        self._paused = False
        self._protocol = protocol


    def read(self):
        """
        Block until there is data available, then return it.
        """
        if self._disconnected is not None:
            self._disconnected.raiseException()
        if self._protocol._buffer != "":
            buffer, self._protocol._buffer = self._protocol._buffer, ""
            return buffer
        self._state = READING
        x = MAIN.switch()
        self._state = None
        return x


    def write(self, data):
        """
        Write the given data to the transport.

        This may block if the write buffer is full.

        @param data: The data to write.
        @type data: C{str}
        """
        if self._disconnected is not None:
            self._disconnected.raiseException()
        if self._paused:
            self._state = WRITING
            MAIN.switch()
            self._state = None
        self._transport.write(data)


    def close(self):
        """
        Close the connection.
        """
        self._transport.loseConnection()



class _GreenletProtocol(Protocol):
    """
    A protocol which calls a greenlet to handle the connection.
    """

    def __init__(self, function):
        """
        @param function: A callable that will be passed one argument, an
            instance of L{GreenletTransport}.
        """
        self.function = function


    def connectionMade(self):
        """
        Initiate the connection by switching to the greenlet.
        """
        self._buffer = ""
        self.greenlet = greenlet(self.function)
        self.gtransport = GreenletTransport(self.transport, self)
        self.transport.registerProducer(self, True)
        self.greenlet.switch(self.gtransport)


    def pauseProducing(self):
        """
        Indicate to the L{GreenletTransport} that future C{write}s should
        block until L{resumeProducing} is called.
        """
        self.gtransport._paused = True


    def resumeProducing(self):
        """
        Unpause the L{GreenletTransport} and cause the blocking C{write} call
        to return.
        """
        # I'm pretty sure you can't possibly be doing anything other than
        # writing if resumeProducing is called.
        assert self.gtransport._state == WRITING
        assert self.gtransport._paused == True
        self.gtransport._paused = False
        self.greenlet.switch()


    def stopProducing(self):
        """
        Do nothing.  We're already avoiding writing data at this point because
        connectionLost has already been called or will be called soon.
        """


    def dataReceived(self, data):
        """
        If the greenlet is currently reading, send the data to it.  Otherwise,
        buffer it, and the next call to L{GreenletTransport.read} will
        immediately return.
        """
        self._buffer += data
        if self.gtransport._state == READING:
            buffer, self._buffer = self._buffer, ""
            self.greenlet.switch(buffer)


    def connectionLost(self, reason):
        """
        Record that the connection is lost, and if the greenlet is currently
        performing I/O, throw C{reason}'s exception into it.
        L{GreenletTransport} will raise that exception for any further I/O
        operations.
        """
        self.gtransport._disconnected = reason
        if self.gtransport._state in (READING, WRITING):
            reason.throwExceptionIntoGenerator(self.greenlet)



class _GreenletFactory(Factory):
    """
    A simple factory which creates L{_GreenletProtocol}s.
    """
    def __init__(self, function):
        """
        @param function: A greenlet function which will be used as per
        L{_GreenletProtocol}.
        """
        self.function = function


    def buildProtocol(self, addr):
        """
        @rtype: L{_GreenletProtocol}.
        """
        return _GreenletProtocol(self.function)



def gListenTCP(port, function, reactor=None):
    """
    Listen for TCP connections and handle them with the given greenlet
    function.  The function will be called in a new greenlet for each incoming
    connection, and will be passed an instance of L{GreenletTransport}.

    @param port: The port number to listen on.
    @type port: C{int}
    @param function: The greenlet function to call for each incoming connection.
    @type function: Callable of one argument, L{GreenletTransport}
    """
    if reactor is None:
        from twisted.internet import reactor
    reactor.listenTCP(port, _GreenletFactory(function))



class _GreenletClientProtocol(_GreenletProtocol):
    """
    A GreenletProtocol which is specialized for client connections.

    Mostly this exists because of special needs in L{connectionMade}.
    """

    def __init__(self, deferred, greenlet):
        """
        @param deferred: A Deferred to fire when a connection is made.
        @param greenlet: The greenlet to hook up to the L{GreenletTransport}.
        """
        self._deferred = deferred
        self.greenlet = greenlet


    def connectionMade(self):
        """
        Fire the previously specified deferred with a fresh
        L{GreenletTransport}.
        """
        self._buffer = ""
        self.transport.registerProducer(self, True)
        self.gtransport = GreenletTransport(self.transport, self)
        self._deferred.callback(self.gtransport)



def gConnectTCP(host, port, reactor=None):
    """
    Return a L{GreenletTransport} connected to the given host and port.

    This function must NOT be called from the reactor's greenlet.
    """
    from corotwine.defer import blockOn
    current = greenlet.getcurrent()
    assert current is not MAIN, \
        "Don't run gConnectTCP from the reactor greenlet."
    if reactor is None:
        from twisted.internet import reactor
    d = Deferred()
    f = ClientFactory()
    f.protocol = lambda: _GreenletClientProtocol(d, current)
    reactor.connectTCP(host, port, f)
    return blockOn(d)
