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

from ..server import collect_process_status, WebServerBase

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

    def fork(self, num_processes):
        if num_processes == 0:
            num_processes = multiprocessing.cpu_count()

        children = {}
        for child_id in range(num_processes):
            # scoketpair使えば良い気がする
            child_id += 1

            c, s = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)

            proc = multiprocessing.Process(target=self._run_child, args=(child_id, c))
            s = ManamgenetSocket(s, self.handle_management_request)
            children[child_id] = ChildServer(proc, s)
            proc.start()

        return children

    def _run_child(self, child_id, management_socket):
        logger.info('forked child web server started')
        self.is_master = False

        server = ChildForkServer(child_id, self.sockets, management_socket, self.app, self.listen)
        # override naumanni_app.webserver
        self.app.webserver = server
        server.start()

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

    async def handle_management_request(self, request, options):
        if request == MANAGEMENT_REQUEST_GET_CHILD_STATUS:
            return collect_process_status()
        else:
            logger.error('Bad request %s:%r', requset, options)

    async def collect_server_status(self):
        """親プロセスに、全体のstatusを要求する"""
        status = await self.management_socket.send_request('get_status')
        return status


# TODO あとでうつす
class ManamgenetSocket(object):
    def __init__(self, sock, callback):
        self._sock = sock
        self._counter = 0
        self._callback = callback
        sock.setblocking(False)

        self._responses = {}
        # ここでcontionを作るとioloopが作られてしまうので、install()まで作らない
        self._response_wait_condition = None

    def install(self):
        io_loop = ioloop.IOLoop.current()
        io_loop.add_handler(self._sock, self.handle_socket_event, ioloop.IOLoop.READ)
        self._response_wait_condition = locks.Condition()

    def handle_socket_event(self, fd, events):
        logger.debug('handle_socket_event %r', events & ioloop.IOLoop.READ)
        assert fd == self._sock

        if events & ioloop.IOLoop.READ:
            # read messages
            while True:
                try:
                    data, ancdata, msg_flags, address = self._sock.recvmsg(MAX_MESSAGE_SIZE)
                except BlockingIOError:
                    break

                logger.debug('  recv %r %r %r %r', data, ancdata, msg_flags, address)
                ioloop.IOLoop.current().add_callback(self.handle_read, data, ancdata, msg_flags, address)

    async def handle_read(self, data, ancdata, msg_flags, address):
        """受けたメッセージを見て、なんかやる"""
        message = json.loads(data)

        if 'request' in message:
            # request is message
            request, token, options = message['request'], message['token'], message['options']
            response = await self._callback(request, options)

            # send response
            res = dict(token=token, response=response)
            payload = json.dumps(res).encode('utf-8')
            if len(payload) >= MAX_MESSAGE_SIZE:
                raise ValueError('response payload exceeded MAX_MESSAGE_SIZE')
            self._sock.sendmsg([payload])

        elif 'response' in message:
            response, token = message['response'], message['token']
            self._responses[token] = response
            self._response_wait_condition.notify_all()

    async def send_request(self, request, **kwargs):
        token = '{:d}{:04x}'.format(int(time.time() * 1000), self._counter)
        logger.debug('send request: %s:%s:%r', request, token, kwargs)
        self._counter += 1

        # send request
        req = dict(request=request, token=token, options=kwargs)
        payload = json.dumps(req).encode('utf-8')
        if len(payload) >= MAX_MESSAGE_SIZE:
            raise ValueError('request payload exceeded MAX_MESSAGE_SIZE')
        self._sock.sendmsg([payload])
        response = await self.pop_response(token)

        return response

    async def pop_response(self, token):
        while True:
            logger.debug('pop_response: %s in %r', token, list(self._responses.keys()))
            rv = self._responses.pop(token, NOT_FOUND)
            if rv is not NOT_FOUND:
                return rv
            await self._response_wait_condition.wait()

# def recv_fds(sock, msglen, maxfds):
#     fds = array.array("i")   # Array of ints
#     msg, ancdata, flags, addr = sock.recvmsg(msglen, socket.CMSG_LEN(maxfds * fds.itemsize))
#     for cmsg_level, cmsg_type, cmsg_data in ancdata:
#         if (cmsg_level == socket.SOL_SOCKET and cmsg_type == socket.SCM_RIGHTS):
#             # Append data, ignoring any truncated integers at the end.
#             fds.fromstring(cmsg_data[:len(cmsg_data) - (len(cmsg_data) % fds.itemsize)])
#     return msg, list(fds)

# signal handling
def install_master_signal_handlers(webserver):
    # SIGTERMされてもちゃんと終了するように
    def stop_handler(webserver, sig, frame):
        io_loop = ioloop.IOLoop.current()
        try:
            for child in webserver.children.values():
                try:
                    os.kill(child.proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            io_loop.add_callback_from_signal(io_loop.stop)
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

        def shutdown():
            logger.info('Stopping http server')
            webserver.app.emit('before-stop-server')
            webserver.http_server.stop()
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
