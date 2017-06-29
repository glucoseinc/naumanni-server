# -*- coding: utf-8 -*-
import json

from tornado import gen, ioloop, locks, netutil, web


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

    def uninstall(self):
        io_loop = ioloop.IOLoop.current()
        io_loop.remove_handler(self._sock)

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
