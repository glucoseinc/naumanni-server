# -*- coding:utf-8 -*-
import functools

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
