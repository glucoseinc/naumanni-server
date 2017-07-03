# -*- coding: utf-8 -*-
import asyncio
import collections
import functools
import logging
import multiprocessing
import os
import signal
import socket
import time
import weakref

from tornado import gen, ioloop, netutil
from tornado.platform.asyncio import AsyncIOLoop, AsyncIOMainLoop, BaseAsyncIOLoop
import tornado.process

from .management_socket import ManamgenetSocket
from .server import collect_process_status, WebServerBase


FORK_MASTER_ID = -1
logger = logging.getLogger(__name__)
MAX_WAIT_SECONDS_BEFORE_SHUTDOWN = 5
ChildServer = collections.namedtuple('ChildServer', ['proc', 'management_socket'])


MANAGEMENT_REQUEST_GET_STATUS = 'get_status'
MANAGEMENT_REQUEST_GET_CHILD_STATUS = 'get_child_status'
MANAGEMENT_REQUEST_SUSPEND_CHILD_SERVER = 'suspend_child_server'


class ForkWebServer(object):
    """master fork webserver"""
    def __init__(self, naumanni_app, listen):
        self.naumanni_app = weakref.ref(naumanni_app)
        self.listen = listen
        self.is_master = True
        self.children = {}

    @property
    def app(self):
        return self.naumanni_app()

    def start(self):
        # install signal handlers for master proc
        install_master_signal_handlers(self)

        # HTTPの待受ポートを開く
        self.sockets = netutil.bind_sockets(*self.app.config.listen)
        self.fork(getattr(self.app.config, 'fork_processes', 0))

        # use asyncio for ioloop
        AsyncIOMainLoop().install()
        io_loop = ioloop.IOLoop.current()

        # setup!
        io_loop.run_sync(functools.partial(self.app.setup, FORK_MASTER_ID))

        # 30分毎に子プロセスの状況を監視して、メモリ食いを殺す
        self.report_task = ioloop.PeriodicCallback(
            self.sweep_fat_child,
            30 * 60 * 1000,
        )
        self.report_task.start()

        for child in self.children.values():
            child.management_socket.install()

    def run(self):
        logger.debug('run master')
        io_loop = ioloop.IOLoop.current()
        try:
            io_loop.start()
        finally:
            logger.debug('master ioloop exited')
            asyncio_loop = asyncio._get_running_loop()
            if asyncio_loop:
                asyncio_loop.run_until_complete(asyncio_loop.shutdown_asyncgens())

    def stop(self):
        # 子サーバーを全部止める
        logger.debug('stop master webserver')
        for child in self.children.values():
            try:
                os.kill(child.proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    def post_stop(self):
        for child_id, child in self.children.items():
            child.proc.join()

    def fork(self, num_processes):
        if num_processes == 0:
            num_processes = multiprocessing.cpu_count()

        for child_id in range(num_processes):
            self.spawn_child(child_id)

    def spawn_child(self, child_id):
        logger.debug('spawn child process child_id:%d', child_id)
        c, s = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        proc = multiprocessing.Process(target=_run_child, args=(self, child_id, c.dup()))
        s = ManamgenetSocket(s, self.handle_management_request)
        self.children[child_id] = ChildServer(proc, s)
        proc.start()

        return self.children[child_id]

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

    async def suspend_child_server(self, child_id):
        """子プロセスを殺して、新しいのを立ち上げ直す"""
        if child_id not in self.children:
            raise ValueError('invalid child id {!r}'.format(child_id))

        old_child = self.children.pop(child_id)
        old_child.management_socket.uninstall()

        # kill child
        try:
            os.kill(old_child.proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

        # spawn new instance
        new_child = self.spawn_child(child_id)
        new_child.management_socket.install()

        logger.debug(
            'respawn child process child_id:%d old_pid:%d new_pid:%d',
            child_id, old_child.proc.pid, new_child.proc.pid)

    async def handle_management_request(self, request, options):
        if request == MANAGEMENT_REQUEST_GET_STATUS:
            # statusが欲しいリクエスト
            # 全子プロセスから集める
            return await self.collect_server_status()
        elif request == MANAGEMENT_REQUEST_SUSPEND_CHILD_SERVER:
            # 非同期でsuspendする
            ioloop.IOLoop.current().add_callback(
                self.suspend_child_server, options['child_id']
            )
            return {}
        else:
            logger.error('Bad request %s:%r', request, options)

    async def sweep_fat_child(self):
        """デブな子供を殺す"""
        max_uss = getattr(self.app.config, 'harakiri_uss_size', 512)
        logger.debug('sweep_fat_child')

        server_status = await self.collect_server_status()
        for child_id, info in server_status['process'].items():
            logger.debug('harakiri check %d -> %f', child_id, info['process.uss'])

            if info['process.uss'] > max_uss:
                child = self.children[child_id]
                logger.info('harakiri child proc(%d, pid=%d). USS=%f', child_id, child.proc.pid, info['process.uss'])
                break


def _run_child(master, child_id, management_socket):
    logger.info('forked child web server started')
    master.is_master = False

    # refresh ioloop environment
    # サーバ起動中に再起動した子プロセスは、親のioloopを引き継いでforkされてくるので、ここですべて殺す
    assert asyncio._get_running_loop() is None
    if ioloop.IOLoop.initialized():
        logger.debug('ioloop is existing (may be I am respawned new child). clear existing ioloops.')

        ioloop.IOLoop.clear_current()
        ioloop.IOLoop.clear_instance()

    server = ChildForkServer(child_id, master.sockets, management_socket, master.app, master.listen)
    # override naumanni_app.webserver
    server.app.webserver = server
    server.start()

    # check asyncio env
    assert ioloop.IOLoop.initialized()
    assert isinstance(ioloop.IOLoop.current(), BaseAsyncIOLoop)
    assert asyncio._get_running_loop() is None

    def checker():
        assert asyncio._get_running_loop() == ioloop.IOLoop.current().asyncio_loop

    ioloop.IOLoop.current().add_callback(checker)
    server.run()


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
        assert not ioloop.IOLoop.initialized()
        AsyncIOLoop().install()
        self.management_socket.install()

    def stop(self):
        """webserverを止める"""
        from .websocket import WebsocketProxyHandler

        for handler in WebsocketProxyHandler.list_handlers():
            handler.close()

        super().stop()
        self.management_socket.uninstall()

    async def handle_management_request(self, request, options):
        if request == MANAGEMENT_REQUEST_GET_CHILD_STATUS:
            return collect_process_status()
        else:
            logger.error('Bad request %s:%r', request, options)

    async def collect_server_status(self):
        """親プロセスに、全体のstatusを要求する"""
        status = await self.management_socket.send_request(MANAGEMENT_REQUEST_GET_STATUS)
        return status

    async def suspend_child_server(self, child_id):
        response = await self.management_socket.send_request(
            MANAGEMENT_REQUEST_SUSPEND_CHILD_SERVER, child_id=child_id)
        return response


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
    logger.debug('debug print ioloop handlers %r --------', io_loop)
    if hasattr(io_loop, '_callbacks'):
        for cb in io_loop._callbacks:
            logger.info('callback %r', cb)
        for to in io_loop._timeouts:
            logger.info('timeout  %r', to)
    elif hasattr(io_loop, 'handlers'):
        for fd, (fileobj, handler_func) in io_loop.handlers.items():
            logger.info('handler  %r %r %r', fd, fileobj, handler_func)
