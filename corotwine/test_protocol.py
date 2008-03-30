"""
Tests for L{corotwine.protocol}.
"""

from cStringIO import StringIO

from twisted.trial.unittest import TestCase
from twisted.test.iosim import FakeTransport
from twisted.internet.error import ConnectionDone, ConnectionLost
from twisted.python.failure import Failure

from twisted.internet.task import Clock

from corotwine.protocol import _GreenletFactory, LineBuffer, gConnectTCP
from corotwine.clock import wait

from py.magic import greenlet


class ServerTests(TestCase):

    def getTransportAndProtocol(self, function):
        """
        Construct a L{GreenletProtocol} with the given C{function} and create a
        L{FakeTransport} to go along with it.

        @param function: Function to pass to L{GreenletProtocol}
        @rtype: Two-tuple of L{FakeTransport}, L{GreenletProtocol}.
        """
        twistedTransport = FakeTransport()
        factory = _GreenletFactory(function)
        protocol = factory.buildProtocol(None)
        twistedTransport.protocol = protocol
        return twistedTransport, protocol


    def connect(self, function):
        """
        Connect the given C{function} via L{GreenletProtocol} to a
        L{FakeTransport}.

        @param function: Function to pass to L{GreenletProtocol}
        @return: A *connected* L{FakeTransport} and L{GreenletProtocol}.
        @rtype: Two-tuple of L{FakeTransport}, L{GreenletProtocol}.
        """
        transport, protocol = self.getTransportAndProtocol(function)
        protocol.makeConnection(transport)
        return transport, protocol


    def test_read(self):
        """
        The transport that is passed to a protocol function can be read from
        to receive data that is received with the Protocol's C{dataReceived}
        method.
        """
        data = []
        def reader(transport):
            data.append(transport.read())

        twistedTransport, protocol = self.connect(reader)
        protocol.dataReceived("foo")
        self.assertEquals(data, ["foo"])


    def test_multipleReads(self):
        """
        After transport.read() returns, more data can be read.
        """
        data = []
        def multiReader(transport):
            for i in range(3):
                data.append(transport.read())
        twistedTransport, protocol = self.connect(multiReader)
        protocol.dataReceived("foo")
        self.assertEquals(data, ["foo"])
        protocol.dataReceived("bar")
        self.assertEquals(data, ["foo", "bar"])
        protocol.dataReceived("baz")
        self.assertEquals(data, ["foo", "bar", "baz"])


    def test_write(self):
        """
        C{transport.write} sends data to the underlying Twisted transport.
        """
        def echo(transport):
            transport.write("hi")
            transport.write("there")

        twistedTransport, protocol = self.connect(echo)
        self.assertEquals(twistedTransport.stream, ["hi", "there"])


    def test_close(self):
        """
        C{transport.close} closes the underlying Twisted transport.
        """
        def close(transport):
            transport.write("foo")
            transport.close()
        twistedTransport, protocol = self.connect(close)
        self.assertTrue(twistedTransport.disconnecting)


    def test_exceptionCloses(self):
        """
        When an exception is raised from the protocol function, the connection
        is closed.
        """
        def explode(transport):
            1/0
        # This test just makes sure that makeConnection propagates the error,
        # since it's higher-up twisted transport stuff that catches errors and
        # closes itself in response.
        twistedTransport, protocol = self.getTransportAndProtocol(explode)
        self.assertRaises(ZeroDivisionError,
                          protocol.makeConnection, twistedTransport)


    def test_exceptionDuringReadingCloses(self):
        """
        Same behavioral test as L{test_exceptionCloses}, but we need to check
        if it also happens in response to a C{dataReceived} call.
        """
        def explode(transport):
            transport.read()
            1/0
        twistedTransport, protocol = self.connect(explode)
        self.assertRaises(ZeroDivisionError, protocol.dataReceived, "foo")


    def test_readOnClosedTransport(self):
        """
        Calling C{transport.read()} when the connection has been lost raises
        the disconnection reason.
        """
        for errorType in (ConnectionLost, ConnectionDone):
            dones = []
            def readOnClosed(transport):
                try:
                    transport.read()
                except errorType, e:
                    dones.append(e)
            twistedTransport, protocol = self.connect(readOnClosed)
            e = errorType("Oops!")
            twistedTransport.disconnectReason = Failure(e)
            twistedTransport.reportDisconnect()
            self.assertEquals(dones, [e])


    def test_writeOnClosedTransport(self):
        """
        If C{transport.write} is called on a disconnected transport,
        the disconnection reason will be raised.
        """
        error = []
        def writeOnClosed(transport):
            # We'll read so that we can get the ConnectionLost.
            try:
                transport.read()
            except Exception, firstE:
                pass
            try:
                transport.write("foo")
            except Exception, secondE:
                assert type(firstE) == type(secondE), (firstE, secondE)
                error.append(secondE)
        twistedTransport, protocol = self.connect(writeOnClosed)
        e = ConnectionLost("Oops!")
        twistedTransport.disconnectReason = Failure(e)
        twistedTransport.reportDisconnect()
        self.assertEquals(error, [e])


    def test_closedTransportOnlyThrowsForIO(self):
        """
        If the I/O greenlet is switched away for a reason other than I/O, a
        connection being lost will not cause the other switched call to
        raise an exception; the exception will be raised the next time an
        I/O operation is done.
        """
        dones = []
        clock = Clock()
        def waitThenRead(transport):
            wait(5, clock)
            try:
                transport.read()
            except ConnectionDone, e:
                dones.append(e)
        twistedTransport, protocol = self.connect(waitThenRead)
        e = ConnectionDone("Oops!")
        twistedTransport.disconnectReason = Failure(e)
        twistedTransport.reportDisconnect()
        clock.advance(5)
        self.assertEquals(dones, [e])


    def test_streamEfficiently(self):
        """
        If the transport's write buffer fills up, C{transport.write} will
        switch to the main greenlet, preventing the greenlet from running
        until the buffer clears.
        """
        def writeALot(transport):
            transport.write("lot")
            transport.write("of data")
        twistedTransport, protocol = self.getTransportAndProtocol(writeALot)

        def write(data):
            originalWrite(data)
            if data == "lot":
                # Whoah, that's a lot!
                twistedTransport.producer.pauseProducing()
        originalWrite = twistedTransport.write
        twistedTransport.write = write
        protocol.makeConnection(twistedTransport)
        self.assertEquals(twistedTransport.stream, ["lot"])
        twistedTransport.producer.resumeProducing()
        self.assertEquals(twistedTransport.stream, ["lot", "of data"])


    def test_incomingDataOnlyGetsSentToReadCalls(self):
        """
        If a call to C{transport.write} caused a switch because the buffer
        was full, incoming data will not be sent to the greenlet.  It will be
        buffered until the next call to C{transport.read}.
        """
        datas = []
        def writeThenRead(transport):
            # We need to write *twice* because it's the *first* write which
            # will trigger the buffer full, and the *second* that will
            # actually block.
            transport.write("lot")
            transport.write("of")
            datas.append(transport.read())
        twistedTransport, protocol = self.getTransportAndProtocol(writeThenRead)

        def write(data):
            twistedTransport.producer.pauseProducing()
        twistedTransport.write = write
        protocol.makeConnection(twistedTransport)
        # Let's receive data multiple times to make sure it's actually
        # *buffering* incoming data, not just dropping it.
        protocol.dataReceived("foo")
        protocol.dataReceived("bar")
        twistedTransport.producer.resumeProducing()
        # make write return, which calls read(), which should immediately
        # return buffered data.
        self.assertEquals(datas, ["foobar"])


    def test_writeRaisesInitialConnectionLost(self):
        """
        If a connectionLost event is received during an outstanding blocked
        call to C{transport.write}, the C{transport.write} call will raise
        the disconnection reason.
        """
        error = []
        def writeLots(transport):
            transport.write("whatever")
            try:
                transport.write("again")
            except Exception, e:
                error.append(e)
        twistedTransport, protocol = self.getTransportAndProtocol(writeLots)

        def write(data):
            twistedTransport.producer.pauseProducing()
        twistedTransport.write = write

        protocol.makeConnection(twistedTransport)
        e = ConnectionLost("hi")
        twistedTransport.disconnectReason = Failure(e)
        twistedTransport.reportDisconnect()
        self.assertEquals(error, [e])


    def test_stopProducing(self):
        """
        L{stopProducing} can be called.

        I don't think we actually need to do anything in the stopProducing
        implementation, because it only ever happens when the transport is
        actually disconnected, which we notice with connectionLost.
        """
        def whatever(transport):
            pass
        twistedTransport, protocol = self.connect(whatever)
        protocol.stopProducing()



class ClientTests(TestCase):
    """
    Tests for the client connection APIs.
    """

    def test_connectWaitsForConnection(self):
        """
        Calling L{gConnectTCP} blocks until a connection is made and returns a
        L{GreenletTransport}.
        """
        transports = []
        def connect():
            transports.append(
                gConnectTCP("whatever", 9090, reactor=fakeReactor))

        class FakeReactor(object):
            def __init__(self):
                self.connections = []
            def connectTCP(self, host, port, factory):
                self.connections.append((host, port, factory))
        fakeReactor = FakeReactor()

        greenlet(connect).switch()
        self.assertEquals(transports, [])
        self.assertEquals(len(fakeReactor.connections), 1)
        self.assertEquals(fakeReactor.connections[0][0], "whatever")
        self.assertEquals(fakeReactor.connections[0][1], 9090)
        proto = fakeReactor.connections[0][2].buildProtocol(None)
        proto.makeConnection(FakeTransport()) # This is gonna switch back!
        self.assertEquals(transports, [proto.gtransport])



class BoringTransport(object):
    """
    A thing with a L{read} method that returns a pre-set sequence of values.
    """
    def __init__(self, reads):
        """
        @param reads: A list of values for L{read} to return in succession.
        """
        self.reads = iter(reads)


    def read(self):
        """
        Return the next value from C{reads}.
        """
        return self.reads.next()



class LineBufferTests(TestCase):
    """
    Tests for the L{LineBuffer}.
    """

    def test_truncateDelimiter(self):
        """
        C{readLine} returns a full line without delimiter.
        """
        io = StringIO("Hello world\r\n")
        wrapper = LineBuffer(io)
        self.assertEquals(wrapper.readLine(), "Hello world")


    def test_buffer(self):
        """
        If C{readLine} cannot immediately get a full line from
        C{transport.read}, it will buffer that data until the next read.
        """
        transport = BoringTransport(["a", "b\r\n"])
        wrapper = LineBuffer(transport)
        self.assertEquals(wrapper.readLine(), "ab")


    def test_multipleLinesInOnePacket(self):
        """
        C{readLine} handles multiple lines in one C{transport.read} result by
        only returning the first and saving the rest for the next call.
        """
        transport = BoringTransport(["foo\r\nbar\r\nbaz\r\n", "quux\r\n"])
        wrapper = LineBuffer(transport)
        self.assertEquals(wrapper.readLine(), "foo")
        self.assertEquals(wrapper.readLine(), "bar")
        self.assertEquals(wrapper.readLine(), "baz")
        self.assertEquals(wrapper.readLine(), "quux")


    def test_multipleLines(self):
        """
        Each call to C{readLine} returns the next line received.
        """
        transport = BoringTransport(["a\r\n", "b\r\n"])
        wrapper = LineBuffer(transport)
        self.assertEquals(wrapper.readLine(), "a")
        self.assertEquals(wrapper.readLine(), "b")


    def test_delimiter(self):
        """
        The delimiter can be whatever you want it to be.
        """
        transport = BoringTransport(["helloxtharx", "yesx"])
        wrapper = LineBuffer(transport, delimiter="x")
        self.assertEquals(wrapper.readLine(), "hello")
        self.assertEquals(wrapper.readLine(), "thar")
        self.assertEquals(wrapper.readLine(), "yes")


    def test_iterate(self):
        """
        The L{LineBuffer} is iterable, and acts as an infinite series of calls
        to C{readLine}.
        """
        transport = BoringTransport(["a\r\nb\r\nc\r\nd"])
        wrapper = LineBuffer(transport)
        iterable = iter(wrapper)
        self.assertEquals(iterable.next(), "a")
        self.assertEquals(iterable.next(), "b")
        self.assertEquals(iterable.next(), "c")


    def test_writeLine(self):
        """
        C{writeLine} is a convenience method for writing some data followed by
        a delimiter.
        """
        io = StringIO()
        wrapper = LineBuffer(io)
        wrapper.writeLine("foo")
        wrapper.writeLine("bar")
        self.assertEquals(io.getvalue(), "foo\r\nbar\r\n")


    def test_writeLineWithDelimiter(self):
        """
        C{writeLine} honors the specified delimiter.
        """
        io = StringIO()
        wrapper = LineBuffer(io, delimiter="Woot,")
        wrapper.writeLine("foo")
        wrapper.writeLine("bar")
        self.assertEquals(io.getvalue(), "fooWoot,barWoot,")
