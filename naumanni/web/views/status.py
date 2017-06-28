# -*- coding:utf-8 -*-
import functools

from tornado import web

from ..base import NaumanniRequestHandlerMixIn


class StatusAPIHandler(web.RequestHandler, NaumanniRequestHandlerMixIn):
    async def get(self):
        last_status = await self._get_status()
        last_time = last_status['date'] if last_status else None

        # sind signal
        os.kill(os.getppid(), signal.SIGUSR1)

        while True:
            status = await self._get_status()
            if status and status['date'] != last_time:
                break

            await gen.sleep(0.5)

        self.write(status)
        await self.flush()

    async def _get_status(self):
        async with self.naumanni_app.get_async_redis() as redis:
            data = await redis.get(REDIS_SERVER_STATUS_KEY)
            return json.loads(data) if data else None


class PingAPIHandler(web.RequestHandler):
    async def get(self):
        self.write('pong')
        await self.flush()
