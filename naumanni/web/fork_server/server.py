# -*- coding: utf-8 -*-
import functools
import logging
import multiprocessing
import os
import signal
import time

from tornado import gen, ioloop, netutil, web
from tornado.platform.asyncio import AsyncIOMainLoop
import tornado.process

from ..server import WebServerBase

logger = logging.getLogger(__name__)
MAX_WAIT_SECONDS_BEFORE_SHUTDOWN = 5
REDIS_SERVER_STATUS_KEY = 'naumanni:server_status'
DELIMITER = b'\x00'


class ForkWebServer(object):
    """master fork webserver"""
    def __init__(self, naumanni_app, listen):
        self.naumanni_app = naumanni_app
        self.listen = listen

    def start(self):
        # install signal handlers for master proc
        install_master_signal_handlers(self)

        # HTTPの待受ポートを開く
        self.sockets = netutil.bind_sockets(*self.naumanni_app.config.listen)
        self.children = self.fork(0)

        # use asyncio for ioloop
        AsyncIOMainLoop().install()

        # run self.naumanni_app.setup(None) synchronusly
        io_loop = ioloop.IOLoop.current()
        io_loop.run_sync(functools.partial(self.naumanni_app.setup, None))

        # master run loop
        io_loop.start()

        for child_id, child in self.children.items():
            child.join()

    def fork(self, num_processes):
        if num_processes == 0:
            num_processes = multiprocessing.cpu_count()

        children = {}
        for child_id in range(num_processes):
            # scoketpair使えば良い気がする
            child_id += 1
            proc = multiprocessing.Process(target=self._run_child, args=(child_id,))
            children[child_id] = proc
            proc.start()

        return children

    def _run_child(self, child_id):
        logger.info('Child process PID:%s', os.getpid())

        server = ChildForkServer(child_id, self.sockets, self.naumanni_app, self.listen)
        server.start()


class ChildForkServer(WebServerBase):
    def __init__(self, child_id, sockets, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.child_id = child_id
        self.sockets = sockets

    def start(self):
        tornado.process._reseed_random()
        install_child_signal_handlers(self)

        # use asyncio for ioloop
        AsyncIOMainLoop().install()

        # run forever
        self._run_server(self.child_id)


# signal handling
def install_master_signal_handlers(webserver):
    # SIGTERMされてもちゃんと終了するように
    def stop_handler(webserver, sig, frame):
        io_loop = ioloop.IOLoop.current()
        try:
            for child in webserver.children.values():
                try:
                    os.kill(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            io_loop.add_callback_from_signal(io_loop.stop)
        except Exception as exc:
            logger.exception(exc)

    handler = functools.partial(stop_handler, webserver)
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGQUIT, handler)
    signal.signal(signal.SIGTERM, handler)

    # status情報収集用ハンドラ
    def status_handler(webserver, sig, frame):
        async def show_server_status(webserver):
            status = await webserver.collect_server_status()
            await webserver.save_server_status(status)
            logger.info('Server status: %r', status)
        ioloop.IOLoop.instance().add_callback_from_signal(show_server_status, webserver)

    signal.signal(signal.SIGUSR1, functools.partial(status_handler, webserver))


def install_child_signal_handlers(webserver):
    """子プロセスがgracefulに死ぬように"""
    def stop_handler(webserver, sig, frame):
        io_loop = ioloop.IOLoop.instance()

        def stop_loop(deadline):
            now = time.time()
            if now < deadline and has_ioloop_tasks(io_loop):
                logger.info('Waiting for next tick...')
                io_loop.add_timeout(now + 1, stop_loop, deadline)
            else:
                io_loop.stop()
                logger.info('Shutdown finally')

        def shutdown():
            logger.info('Stopping http server')
            webserver.naumanni_app.emit('before-stop-server')
            webserver.http_server.stop()
            logger.info('Will shutdown in %s seconds ...', MAX_WAIT_SECONDS_BEFORE_SHUTDOWN)
            stop_loop(time.time() + MAX_WAIT_SECONDS_BEFORE_SHUTDOWN)

        io_loop.add_callback_from_signal(shutdown)

    handler = functools.partial(stop_handler, webserver)
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGQUIT, handler)
    signal.signal(signal.SIGTERM, handler)

    def status_handler(webserver, sig, frame):
        io_loop = ioloop.IOLoop.instance()

        async def _send_status(webserver):
            status = _collect_status()
            await webserver.pipe_writer.write(json.dumps(status).encode('latin1') + DELIMITER)

        io_loop.add_callback_from_signal(_send_status, webserver)

    signal.signal(signal.SIGUSR1, functools.partial(status_handler, webserver))


def _collect_status():
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


def has_ioloop_tasks(io_loop):
    if hasattr(io_loop, '_callbacks'):
        return io_loop._callbacks or io_loop._timeouts
    elif hasattr(io_loop, 'handlers'):
        return len(io_loop.handlers)
    return False
