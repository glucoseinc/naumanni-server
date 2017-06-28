# -*- coding: utf-8 -*-
import asyncio
import collections
import logging
import functools
import json
import multiprocessing
import os
import signal
import socket
import time

import psutil
from tornado import gen, ioloop, iostream, routing, web
from tornado.httpserver import HTTPServer
from tornado.wsgi import WSGIContainer
import tornado.netutil
import tornado.process
from tornado.platform.asyncio import AsyncIOMainLoop

from .base import NaumanniRequestHandlerMixIn
from .proxy import APIProxyHandler
from .websocket import WebsocketProxyHandler
from .views.status import StatusAPIHandler, PingAPIHandler


logger = logging.getLogger(__name__)


class NaumanniWebApplication(web.Application):
    def add_plugin_handlers(self, plugin_id, handlers):
        """plugin apiを追加する"""

        # plugin apiのprefixをURLに追加する
        path_prefix = '/plugins/{}/'.format(plugin_id)
        replaced_handlers = []
        for rule in handlers:
            if isinstance(rule, (tuple, list)):
                if isinstance(rule[0], str):
                    if not rule[0].startswith('/'):
                        raise ValueError('invalid plugin url path, must be startswith \'/\'')
                    rule = (path_prefix + rule[0][1:], *rule[1:])
                else:
                    assert 0, 'not implemented'
            else:
                assert 0, 'not implemented'

            replaced_handlers.append(rule)

        # 登録
        self.wildcard_router.add_rules(
            [(path_prefix + '.*$', web._ApplicationRouter(self, replaced_handlers))]
        )


class WebServerBase(object):
    def __init__(self, naumanni_app, listen):
        self.naumanni_app = naumanni_app
        self.listen = listen

        self.init()

    def init(self):
        handlers = [
            (r'/proxy/(?P<request_url>.+)', APIProxyHandler),
            (r'/ws/(?P<request_url>.+)', WebsocketProxyHandler),
            (r'/status', StatusAPIHandler),
            (r'/ping', PingAPIHandler),
        ]
        self.application = NaumanniWebApplication(
            handlers,
            compress_response=True,
            debug=self.naumanni_app.debug,
            autoreload=False,
            websocket_ping_interval=3,
            naumanni_app=self.naumanni_app,
        )
        self.naumanni_app.emit('after-initialize-webserver', webserver=self)

    def _run_server(self, child_id):
        assert AsyncIOMainLoop().initialized()

        # run self.naumanni_app.setup(child_id) synchronusly
        io_loop = ioloop.IOLoop.current()
        io_loop.run_sync(functools.partial(self.naumanni_app.setup, child_id))

        self.http_server = HTTPServer(self.application)
        self.http_server.add_sockets(self.sockets)

        # run ioloop
        ioloop.IOLoop.current().start()

    async def save_server_status(self, status):
        """statusをredisに保存する"""
        async with self.naumanni_app.get_async_redis() as redis:
            status['date'] = time.time()
            await redis.set(REDIS_SERVER_STATUS_KEY, json.dumps(status))

    async def collect_server_status(self):
        raise NotImplementedError()


class DebugWebServer(WebServerBase):
    def start(self):
        self.sockets = tornado.netutil.bind_sockets(*self.naumanni_app.config.listen)
        # debugなのでautoreloadする
        AsyncIOMainLoop().install()
        from tornado import autoreload
        autoreload.start()

        self._run_server(None)
