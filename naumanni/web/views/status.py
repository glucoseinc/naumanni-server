# -*- coding:utf-8 -*-
from tornado import web

from ..base import NaumanniRequestHandlerMixIn


class StatusAPIHandler(web.RequestHandler, NaumanniRequestHandlerMixIn):
    async def get(self):
        webserver = self.naumanni_app.webserver

        status = await webserver.collect_server_status()
        self.write(status)
        await self.flush()


class PingAPIHandler(web.RequestHandler):
    async def get(self):
        self.write('pong')
        await self.flush()


class DebugSuspendHandler(web.RequestHandler, NaumanniRequestHandlerMixIn):
    """指定されたchildプロセスをサスペンドさせる"""
    async def get(self, child_id):
        child_id = int(child_id, 10)

        webserver = self.naumanni_app.webserver
        await webserver.suspend_child_server(child_id)
