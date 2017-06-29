# -*- coding: utf-8 -*-
import asyncio
import collections
import functools
import json
import logging
import os
import signal
import socket
import time
import weakref

import psutil
from tornado import gen, ioloop, iostream, routing, web
from tornado.httpserver import HTTPServer
import tornado.netutil
from tornado.platform.asyncio import AsyncIOMainLoop
import tornado.process
from tornado.wsgi import WSGIContainer

from .base import NaumanniRequestHandlerMixIn
from .proxy import APIProxyHandler
from .views.status import DebugSuspendHandler, PingAPIHandler, StatusAPIHandler
from .websocket import WebsocketProxyHandler


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
        self.child_id = None
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

            (r'/debug/suspend/(?P<child_id>\d+)', DebugSuspendHandler),
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

    def start(self):
        pass

    def run(self):
        if not AsyncIOMainLoop().initialized():
            AsyncIOMainLoop().install()

        logger.debug('run')

        io_loop = ioloop.IOLoop.current()
        io_loop.run_sync(functools.partial(self.app.setup, self.child_id))

        self.http_server = HTTPServer(self.application)
        self.http_server.add_sockets(self.sockets)

        try:
            io_loop.start()
        finally:
            logger.debug('runloop exited')

            # finalize asyncio
            import asyncio

            asyncio_loop = asyncio.get_event_loop()
            assert not asyncio_loop.is_running()
            asyncio_loop.run_until_complete(asyncio_loop.shutdown_asyncgens())
            asyncio_loop.close()

    def stop(self):
        """webserverを止める"""
        self.http_server.stop()

    async def collect_server_status(self):
        raise NotImplementedError()


class DebugWebServer(WebServerBase):
    def start(self):
        self.sockets = tornado.netutil.bind_sockets(*self.app.config.listen)
        # debugなのでautoreloadする
        AsyncIOMainLoop().install()
        from tornado import autoreload
        autoreload.start()

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
