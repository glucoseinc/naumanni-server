# -*- coding: utf-8 -*-
import collections
import functools
import json
import logging
import multiprocessing
import os
import signal
import socket
import time
import weakref

from tornado import gen, ioloop, locks, netutil, web
from tornado.platform.asyncio import AsyncIOMainLoop
import tornado.process

from .management_socket import ManamgenetSocket
from .server import collect_process_status, WebServerBase


logger = logging.getLogger(__name__)
MAX_WAIT_SECONDS_BEFORE_SHUTDOWN = 5
DELIMITER = b'\x00'
MAX_MESSAGE_SIZE = 5120
NOT_FOUND = object()

ChildServer = collections.namedtuple('ChildServer', ['proc', 'management_socket'])


MANAGEMENT_REQUEST_GET_STATUS = 'get_status'
MANAGEMENT_REQUEST_GET_CHILD_STATUS = 'get_child_status'


class ForkWebServer(object):
    """master fork webserver"""
    def __init__(self, naumanni_app, listen):
        self.naumanni_app = weakref.ref(naumanni_app)
        self.listen = listen

        self.is_master = True

    @property
    def app(self):
        return self.naumanni_app()

    def start(self):
        # install signal handlers for master proc
        install_master_signal_handlers(self)

        # HTTPの待受ポートを開く
        self.sockets = netutil.bind_sockets(*self.app.config.listen)
        self.children = self.fork(getattr(self.app.config, 'fork_processes', 0))

        # use asyncio for ioloop
        AsyncIOMainLoop().install()

        for child in self.children.values():
            child.management_socket.install()

        # master run loop
        io_loop.start()

        for child_id, child in self.children.items():
            child.proc.join()

    def stop(self):
        # 子サーバーを全部止める
        logger.debug('stop master webserver')
        for child in self.children.values():
            try:
                os.kill(child.proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    def fork(self, num_processes):
        if num_processes == 0:
            num_processes = multiprocessing.cpu_count()

        children = {}
        for child_id in range(num_processes):
            # scoketpair使えば良い気がする
            child_id += 1

            c, s = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)

            proc = multiprocessing.Process(target=_run_child, args=(self, child_id, c))
            s = ManamgenetSocket(s, self.handle_management_request)
            children[child_id] = ChildServer(proc, s)
            proc.start()

        return children

    async def collect_server_status(self):
        async def _pair(cid, future):
            return (cid, await future)

        status = {
            'process': {},
            'date': time.time(),
        }

        responses = await gen.multi([
            _pair(child_id, child.management_socket.send_request(MANAGEMENT_REQUEST_GET_CHILD_STATUS))
            for child_id, child in self.children.items()
        ])
        logger.debug('responses %r', responses)
        for cid, child_status in responses:
            status['process'][cid] = child_status

            for key in ['io_loop.handlers', 'io_loop.selector.fds', 'process.rss', 'process.uss']:
                status[key] = status.get(key, 0) + child_status[key]

        return status

    async def handle_management_request(self, request, options):
        if request == MANAGEMENT_REQUEST_GET_STATUS:
            # statusが欲しいリクエスト
            # 全子プロセスから集める
            return await self.collect_server_status()
        else:
            logger.error('Bad request %s:%r', requset, options)


def _run_child(master, child_id, management_socket):
    logger.info('forked child web server started')
    master.is_master = False

    server = ChildForkServer(child_id, master.sockets, management_socket, master.app, master.listen)
    # override naumanni_app.webserver
    master.app.webserver = server
    server.start()


class ChildForkServer(WebServerBase):
    def __init__(self, child_id, sockets, management_socket, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.child_id = child_id
        self.sockets = sockets
        self.management_socket = ManamgenetSocket(management_socket, self.handle_management_request)

    def start(self):
        tornado.process._reseed_random()
        install_child_signal_handlers(self)

        # use asyncio for ioloop
        AsyncIOMainLoop().install()

        self.management_socket.install()

        # run forever
        self._run_server(self.child_id)

    def stop(self):
        """webserverを止める"""
        super().stop()
        self.management_socket.uninstall()

    async def handle_management_request(self, request, options):
        if request == MANAGEMENT_REQUEST_GET_CHILD_STATUS:
            return collect_process_status()
        else:
            logger.error('Bad request %s:%r', requset, options)

    async def collect_server_status(self):
        """親プロセスに、全体のstatusを要求する"""
        status = await self.management_socket.send_request('get_status')
        return status


# signal handling
def install_master_signal_handlers(webserver):
    # SIGTERMされてもちゃんと終了するように
    def stop_handler(webserver, sig, frame):
        io_loop = ioloop.IOLoop.current()

        async def stopper():
            await webserver.app.stop()
            io_loop.stop()

        try:
            io_loop.add_callback_from_signal(stopper)
        except Exception as exc:
            logger.exception(exc)

    handler = functools.partial(stop_handler, webserver)
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGQUIT, handler)
    signal.signal(signal.SIGTERM, handler)


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

        async def shutdown():
            logger.info('Stopping child http server')
            await webserver.app.stop()
            logger.info('Will shutdown in %s seconds ...', MAX_WAIT_SECONDS_BEFORE_SHUTDOWN)
            stop_loop(time.time() + MAX_WAIT_SECONDS_BEFORE_SHUTDOWN)

        io_loop.add_callback_from_signal(shutdown)

    handler = functools.partial(stop_handler, webserver)
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGQUIT, handler)
    signal.signal(signal.SIGTERM, handler)


def has_ioloop_tasks(io_loop):
    if hasattr(io_loop, '_callbacks'):
        return io_loop._callbacks or io_loop._timeouts
    elif hasattr(io_loop, 'handlers'):
        return len(io_loop.handlers)
    return False


def debug_list_ioloop_tasks(io_loop):
    logger.debug('debug print ioloop handlers %r', io_loop)
    if hasattr(io_loop, '_callbacks'):
        for cb in io_loop._callbacks:
            logger.info('callback %r', cb)
        for to in io_loop._timeouts:
            logger.info('timeout  %r', to)
    elif hasattr(io_loop, 'handlers'):
        for fd, (fileobj, handler_func) in io_loop.handlers.items():
            logger.info('handler  %r %r %r', fd, fileobj, handler_func)
