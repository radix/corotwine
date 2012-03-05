"""
Some sample protocols. This is meant to be an example; please read the source
code, not the API docs.
"""
import string, random

from twisted.internet.error import ConnectionClosed
from twisted.protocols.amp import AMP, Command, String
from twisted.web.client import getPage

from corotwine.protocol import gListenTCP, gConnectTCP, LineBuffer
from corotwine.defer import blockOn, deferredGreenlet
from corotwine import greenlet


def echo(transport):
    while 1:
        try:
            transport.write(transport.read())
        except ConnectionClosed:
            return


def discard(transport):
    while 1:
        try:
            transport.read()
        except ConnectionClosed:
            return


def qotd(transport):
    transport.write("An apple a day keeps the doctor away.\r\n")


def chargen(transport):
    # Sample of efficient streaming.  transport.write switches back to the
    # reactor greenlet when buffers are full.
    while 1:
        try:
            transport.write(''.join(random.choice(string.letters)
                                    for i in range(1024)))
        except ConnectionClosed:
            return


class Chat(object):
    def __init__(self):
        self.clients = []

    def handleConnection(self, transport):
        transport = LineBuffer(transport)
        self.clients.append(transport)
        try:
            try:
                for line in transport:
                    for client in self.clients:
                        if client is not transport:
                            client.writeLine(line)
            finally:
                self.clients.remove(transport)
        except ConnectionClosed:
            return


def fetchGoogle(transport):
    result = blockOn(getPage("http://google.com/"))
    transport.write(result)



## And an amp example, to show off deferredGreenlet

class FetchGoogle(Command):
    arguments = []
    response = [("google", String())]

class GoogleGetter(AMP):
    @FetchGoogle.responder
    @deferredGreenlet
    def fetchGoogle(self):
        return {"google": blockOn(getPage("http://google.com/"))}



## Clients!

def echoclient():
    transport = gConnectTCP("localhost", 1027)
    transport.write("Heyo!")
    if transport.read() == "Heyo!":
        print "Echo server test succeeded!"
    else:
        print "Echo server test failed :-("


def googleAMPClient():
    from twisted.internet.protocol import ClientCreator
    cc = ClientCreator(reactor, AMP)
    ampConnection = blockOn(cc.connectTCP("localhost", 1030))
    result = blockOn(ampConnection.callRemote(FetchGoogle))
    if "I'm Feeling Lucky" in result["google"]:
        print "Google AMP Client test succeeded"
    else:
        print "Google AMP client test failed :-("
    ampConnection.transport.loseConnection()


# Deployment code

def startServers():
    gListenTCP(1025, discard)
    gListenTCP(1026, qotd)
    gListenTCP(1027, echo)
    gListenTCP(1028, chargen)
    gListenTCP(1029, fetchGoogle)

    from twisted.internet.protocol import Factory
    ampf = Factory()
    ampf.protocol = GoogleGetter
    reactor.listenTCP(1030, ampf)

    chat = Chat()
    gListenTCP(1031, chat.handleConnection)


if __name__ == '__main__':
    from twisted.internet import reactor
    from twisted.python.log import startLogging
    import sys
    startLogging(sys.stdout)

    startServers()
    greenlet(echoclient).switch()

    # Uncomment to test google thingy.
    #greenlet(googleAMPClient).switch()

    reactor.run()
