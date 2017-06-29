# -*- coding: utf-8 -*-
import json
import logging
import re
import time
from urllib.parse import urlparse
import weakref

from tornado import gen, httpclient
from tornado.websocket import (
    websocket_connect, WebSocketClosedError, WebSocketHandler
)

from .base import NaumanniRequestHandlerMixIn
from ..mastodon_api import denormalize_mastodon_response, normalize_mastodon_response


logger = logging.getLogger(__name__)
https_prefix_rex = re.compile('^wss?://?')


class ListHandlersMixin(object):
    __handlers = weakref.WeakSet()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__handlers.add(self)

    @classmethod
    def list_handlers(kls):
        return list(kls.__handlers)


class WebsocketProxyHandler(WebSocketHandler, NaumanniRequestHandlerMixIn, ListHandlersMixin):
    """proxyる

    :param UUID slave_uuid:
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.peer = None  # 相手先MastodonのWS
        self.closed = False

    @gen.coroutine
    def open(self, request_url):
        # TODO: 最近のアクセス状況をみて、無制限に接続されないように
        if self.request.query:
            request_url += '?' + self.request.query
        mo = https_prefix_rex.match(request_url)
        if not mo.group(0).endswith('//'):
            request_url = '{}/{}'.format(mo.group(0), request_url[mo.end():])

        logger.info('peer ws: %s', request_url)
        request = httpclient.HTTPRequest(request_url)
        try:
            self.peer = yield websocket_connect(request, ping_interval=self.ping_interval)
        except Exception as e:
            logger.error('peer connect failed: %r', e)
            raise
        self.listen_peer()

    # WebsocketHandler overrides
    @gen.coroutine
    def on_message(self, plain_msg):
        message = json.loads(plain_msg)
        logger.debug('client: %r' % message)

    def on_close(self):
        """クライアントとの接続が切れた際に呼ばれる."""
        logger.debug('connection closed: %s %s', self.close_code, self.close_reason)
        self.closed = True

        # TODO: 即、サーバ側も閉じる. read_messageをキャンセルする
        if self.peer:
            self.peer.close()

    def check_origin(self, origin):
        """nginxの内側にいるので、check_originに細工が必要"""
        parsed_origin = urlparse(origin)
        origin = parsed_origin.netloc
        origin = origin.lower()

        key = 'X-Forwarded-Server' if 'X-Forwarded-Server' in self.request.headers else 'Host'
        host = self.request.headers.get(key)

        return origin == host

    @gen.coroutine
    def listen_peer(self):
        """閉じられるまで、server側wsのメッセージをlistenする"""
        logger.debug('listen peer')
        while not self.closed:
            raw = yield self.peer.read_message()
            if raw is None:
                # connetion was closed
                logger.info('server conncetion closed')
                self.closed = True
                self.close()
                break

            yield self.on_new_message_from_server(json.loads(raw))
        logger.debug('close peer')

    def pinger(self):
        data = str(time.time()).encode('utf8')
        logger.debug('pinger: %r', data)
        self.ping(data)

    async def on_new_message_from_server(self, message):
        """Mastodonサーバから新しいメッセージが来た"""
        # logger.debug('server: %r...', repr(message)[:80])

        if message['event'] in ('update', 'notification'):
            api = '/__websocket__/{}'.format(message['event'])
            payload = json.loads(message['payload'])
            entities, result = normalize_mastodon_response(api, payload)
            # TODO: _filter_entitiesをどっかに纏める
            from .proxy import _filter_entities
            await _filter_entities(self.naumanni_app, entities)
            payload = denormalize_mastodon_response(api, result, entities)
            message['payload'] = json.dumps(payload)

        # clientにpass
        try:
            self.write_message(json.dumps(message))
        except WebSocketClosedError:
            # TODO: closeメソッドを作る
            self.closed = True
