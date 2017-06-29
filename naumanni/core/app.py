# -*- coding: utf-8 -*-
"""Naumanni Core."""
import asyncio
import inspect
import logging
import os

import aioredis
import pkg_resources
from tornado import concurrent, gen, httpclient

import naumanni
from ..plugin import Plugin

try:
    import config
except:
    config = {}


logger = logging.getLogger(__name__)
USER_AGENT = 'Naumanni/{}'.format(naumanni.VERSION)


class NaumanniApp(object):
    __instance = None

    def __new__(cls, **kwargs):
        if cls.__instance is None:
            cls.__instance = super().__new__(cls)
        else:
            logger.warning('application initialized twice')
        return cls.__instance

    def __init__(self, debug=False):
        self.debug = debug
        self.config = config
        self.root_path = os.path.abspath(os.path.join(naumanni.__file__, os.path.pardir, os.path.pardir))
        self.plugins = self.load_plugins()
        self.webserver = None  # webserver初期化時に代入される
        self._is_closed = False

    def is_closed(self):
        return self._is_closed

    def load_plugins(self):
        assert not hasattr(self, 'plugins')
        plugins = {}
        for ep in pkg_resources.iter_entry_points('naumanni.plugins'):
            plugin = Plugin.from_ep(self, ep)
            plugins[plugin.id] = plugin
            logger.info('Load plugin: %s', plugin.id)
        return plugins

    async def setup(self, child_id):
        """runloop前の最後のセットアップ"""
        self.child_id = child_id
        if not child_id:
            # forkしてたら0, してなければNoneがくる  1st-processなのでtimer系をここにinstall
            self.emit('after-start-first-process')

        host, port, db = self.config.redis
        self._async_redis_pool = await aioredis.create_pool(
            (host, port), db=db, loop=asyncio.get_event_loop()
        )

    async def stop(self):
        """appを終了させる"""
        self._is_closed = True
        self.emit('before-stop-server')

        # http_serverを止める
        self.webserver.stop()
        # redisを止める
        self._async_redis_pool.close()
        await self._async_redis_pool.wait_closed()

    def emit(self, event, **kwargs):
        rv = {}
        _result_hook = kwargs.pop('_result_hook', None)
        funcname = 'on_' + event.replace('-', '_')
        for plugin in self.plugins.values():
            handler = getattr(plugin, funcname, None)
            if handler is not None:
                result = handler(**kwargs)
                assert not inspect.iscoroutinefunction(result)

                rv[plugin.id] = result
                if _result_hook:
                    kwargs = _result_hook(rv[plugin.id], kwargs)

        return rv

    async def emit_async(self, event, **kwargs):
        rv = {}
        _result_hook = kwargs.pop('_result_hook', None)
        funcname = 'on_' + event.replace('-', '_')
        for plugin in self.plugins.values():
            handler = getattr(plugin, funcname, None)
            if handler is not None:
                rv[plugin.id] = await handler(**kwargs)
                if _result_hook:
                    kwargs = _result_hook(rv[plugin.id], kwargs)

        return rv

    # redis
    def get_async_redis(self):
        return self._async_redis_pool.get()

    # utility functions
    async def crawl_url(self, url_or_request):
        """指定されたURLを撮ってきて返す"""
        # TODO: crawler pool的な感じにする
        response = await httpclient.AsyncHTTPClient().fetch(
            url_or_request, follow_redirects=False, raise_error=False, user_agent=USER_AGENT)
        return response


class _AsyncRedisPool(object):
    __slots__ = ('_app', '_conn')

    def __init__(self, app):
        self._app = app
        self._conn = None

    async def __aenter__(self):
        pool = await self._app.async_redis_pool
        self._conn = await pool.acquire()
        return self._conn

    async def __aexit__(self, exc_type, exc_value, tb):
        pool = await self._app.async_redis_pool
        try:
            pool.release(self._conn)
        finally:
            self._app = None
            self._conn = None
