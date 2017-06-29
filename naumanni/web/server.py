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
import weakref

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
        self.naumanni_app = weakref.ref(naumanni_app)
        self.listen = listen

        self.init()

    @property
    def app(self):
        return self.naumanni_app()

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
            debug=self.app.debug,
            autoreload=False,
            websocket_ping_interval=3,
            naumanni_app=self.app,
        )
        self.app.emit('after-initialize-webserver', webserver=self)

    def _run_server(self, child_id):
        assert AsyncIOMainLoop().initialized()

        # run self.naumanni_app.setup(child_id) synchronusly
        io_loop = ioloop.IOLoop.current()
        io_loop.run_sync(functools.partial(self.app.setup, child_id))

        self.http_server = HTTPServer(self.application)
        self.http_server.add_sockets(self.sockets)

        # run ioloop
        ioloop.IOLoop.current().start()

    async def collect_server_status(self):
        raise NotImplementedError()


class DebugWebServer(WebServerBase):
    def start(self):
        self.sockets = tornado.netutil.bind_sockets(*self.app.config.listen)
        # debugなのでautoreloadする
        AsyncIOMainLoop().install()
        from tornado import autoreload
        autoreload.start()

        self._run_server(None)

    async def collect_server_status(self):
        return collect_process_status()


# utils
def collect_process_status():
    io_loop = ioloop.IOLoop.instance()
    selector = io_loop.asyncio_loop._selector

    proc = psutil.Process()
    with proc.oneshot():
        mem = proc.memory_full_info()

        status = {
            'io_loop.handlers': len(io_loop.handlers),
            'io_loop.selector.fds': len(selector._fd_to_key),
            'process.uss': mem.uss / 1024.0 / 1024.0,
            'process.rss': mem.rss / 1024.0 / 1024.0,
        }
    return status
