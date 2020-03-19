import sys 
import os
import json
from urllib.parse import urlparse
from twisted.internet import reactor, protocol, defer, task
from twisted.python import log 
from autobahn.twisted.websocket import WebSocketServerProtocol, WebSocketServerFactory
from autobahn.websocket.types import ConnectionDeny
import pika
from pika import exceptions
from pika.adapters import twisted_connection

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ducx_wish.settings')
import django
django.setup()
from django.http.cookie import parse_cookie
from django.contrib.sessions.models import Session
from django.contrib.auth.models import User
from django.conf import settings

class WSP(WebSocketServerProtocol):
    user = None
    
    def check_origin(self, origin):
        if origin not in ('http://dev.mywish.io', 'http://contracts.mywish.io'):
            raise ConnectionDeny(404)

    def check_auth(self, cookie):
        session_key = cookie.get(settings.SESSION_COOKIE_NAME, '') 
        try:
            session = Session.objects.get(session_key=session_key)
            user_id = session.get_decoded().get('_auth_user_id')
            self.user = User.objects.get(id=user_id, is_active=True)
        except:
            raise ConnectionDeny(403)

    def onConnect(self, request):
        origin = request.headers.get('origin', '') 
#        self.check_origin(origin)
        cookie = parse_cookie(request.headers.get('cookie', ''))
        self.check_auth(cookie)
        return super().onConnect(request)

    def onOpen(self):
        if self.user.id in self.factory.connections_dict.keys():
            self.factory.connections_dict[self.user.id].append(self)
        else:
            self.factory.connections_dict[self.user.id] = [self]
        self.factory.pings_lost[self.peer] = 0
        self.run = True
        self.doPing()

    def onMessage(self, payload, isBinary):
        return

    def onClose(self, wasClean, code, reason):
        self.run = False
        if self.user and self in self.factory.connections_dict[self.user.id]:
            self.factory.connections_dict[self.user.id].remove(self)
        self.factory.pings_lost.pop(self.peer, None)

    def doPing(self):
        if self.run:
            if self.factory.pings_lost[self.peer] >= 3:
                print('closing due to timeout')
                self.sendClose()
            else:
                self.sendPing()
                self.factory.pings_lost[self.peer] += 1
                reactor.callLater(20, self.doPing)

    def onPong(self, payload):
        self.factory.pings_lost[self.peer] = 0




@defer.inlineCallbacks
def run(connection, proto_dict):
    channel = yield connection.channel()
    queue = yield channel.queue_declare(queue='websockets', durable=True, auto_delete=False, exclusive=False)
    queue_object, consumer_tag = yield channel.basic_consume(queue='websockets', no_ack=True)
    l = task.LoopingCall(read, queue_object, proto_dict)
    l.start(0.01)

@defer.inlineCallbacks
def read(queue_object, proto_dict):
    ch, method, properties, body = yield queue_object.get()
    user = int(properties.type)
    print('sending to', user)
    for c in proto_dict.get(user, []):
        yield c.sendMessage(body, False)
    print('sended to', user)

if __name__ == '__main__':
    log.startLogging(sys.stdout)
    factory = WebSocketServerFactory("ws://127.0.0.1:8078")
    factory.protocol = WSP 
    factory.setProtocolOptions(maxConnections=10000)
    factory.connections_dict = {}
    factory.pings_lost = {}

    reactor.listenTCP(8078, factory)
    cc = protocol.ClientCreator(
        reactor,
        twisted_connection.TwistedProtocolConnection,
        pika.ConnectionParameters(
            '127.0.0.1',
            5672,
            'mywill',
            pika.PlainCredentials('java', 'java'),
            heartbeat_interval=0,
        )
    )
    d = cc.connectTCP('127.0.0.1', 5672)
    d.addCallback(lambda protocol: protocol.ready)
    d.addCallback(run, factory.connections_dict)
    reactor.run()
