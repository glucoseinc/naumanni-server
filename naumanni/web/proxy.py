# -*- coding: utf-8 -*-
import json
import logging
import re
from urllib.parse import quote, urlsplit, urlunsplit

from tornado import httpclient, queues
from tornado.curl_httpclient import CurlAsyncHTTPClient
from tornado.simple_httpclient import SimpleAsyncHTTPClient
import tornado.web
from werkzeug.exceptions import NotFound

from .base import NaumanniRequestHandlerMixIn
from ..mastodon_api import denormalize_mastodon_response, normalize_mastodon_response


logger = logging.getLogger(__name__)
https_prefix_rex = re.compile('^https?://?')
mastodon_api_rex = re.compile(r'^https?://(?P<host>[^/]+)/api/v1(?P<api>/.*?)(?:\?.*)?$')
FINISH_MARKER = object()

PASS_REQUEST_HEADERS = [
    'Accept', 'Accept-Language', 'Authorization', 'Content-Type', 'Referer', 'User-Agent'
]
PASS_RESPONSE_HEADERS = [
    'Content-Type', 'Date',
    'X-Frame-Options', 'X-Content-Type-Options', 'X-Xss-Protection', 'X-Ratelimit-Limit', 'X-Ratelimit-Remaining',
    'X-Ratelimit-Reset',
]


@tornado.web.stream_request_body
class APIProxyHandler(tornado.web.RequestHandler, NaumanniRequestHandlerMixIn):
    SUPPORTED_METHODS = ['GET', 'DELETE', 'PATCH', 'POST', 'PUT']

    def prepare(self):
        self.data_queue = queues.Queue()
        self.total_bytes = 0

        self.content_length = None
        if self.request.method in ('PATCH', 'POST', 'PUT'):
            content_length = self.request.headers.get('Content-Length')
            if not content_length:
                # upload request must have Content-Length
                raise tornado.web.HTTPError(405)

            self.content_length = int(content_length, 10)

    def get(self, *args, **kwargs):
        return self.run(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return self.run(*args, **kwargs)

    def patch(self, *args, **kwargs):
        return self.run(*args, **kwargs)

    def post(self, *args, **kwargs):
        return self.run(*args, **kwargs)

    def put(self, *args, **kwargs):
        return self.run(*args, **kwargs)

    def data_received(self, chunk):
        self.data_queue.put(chunk)

        self.total_bytes += len(chunk)
        if self.total_bytes >= self.content_length:
            self.data_queue.put(FINISH_MARKER)

    async def run(self, request_url):
        request_url = self._fix_request_url(request_url)

        # parse api
        mo = mastodon_api_rex.match(request_url)
        self.request_host, self.request_api = mo.groups() if mo else (None, None)

        # apps作る以外は、認証なければNGにしておく
        if self.is_need_authorization() and 'Authorization' not in self.request.headers:
            raise tornado.web.HTTPError(401)
        # TODO: ホスト名チェック

        # pass request to mastodon
        response = await self._pass_request(request_url)
        if response.code == 200:
            response_body = await self._filter_response(request_url, response)
            response_headers = _filter_dict(response.headers, PASS_RESPONSE_HEADERS)
            response_headers['Cache-Control'] = 'max-age=0, private, must-revalidate'
        else:
            response_body, response_headers = response.body, response.headers

        # response
        self.set_status(response.code)
        for k, v in response_headers.items():
            self.set_header(k, v)
        self.write(response_body)
        await self.flush()
        self.finish()

    def is_need_authorization(self):
        # appsは認証がなくても作れてしまう
        if (self.request_api == '/apps' and self.request.method == 'POST'):
            return False
        return True

    def _fix_request_url(self, request_url):
        request_url = request_url.encode('latin1').decode('utf-8')
        if self.request.query:
            request_url = '{}?{}'.format(request_url, self.request.query)

        # fix url
        mo = https_prefix_rex.match(request_url)
        if not mo.group(0).endswith('//'):
            request_url = '{}/{}'.format(mo.group(0), request_url[mo.end():])

        t = urlsplit(request_url)
        request_url = urlunsplit((t[0], t[1], quote(t[2]), t[3], ''))

        return request_url

    async def _pass_request(self, request_url):
        request_args = {}
        pass_headers = PASS_REQUEST_HEADERS
        if self.content_length:
            # CurlAsyncHTTPClientがbody_producerを使えないため
            fetcher = SimpleAsyncHTTPClient
            pass_headers += ['Content-Length']

            async def _produce_body(write):
                async for buf in self.data_queue:
                    if buf is FINISH_MARKER:
                        break
                    write(buf)

            request_args = {
                'body_producer': _produce_body
            }
        else:
            fetcher = CurlAsyncHTTPClient

        # build request
        request = httpclient.HTTPRequest(
            url=request_url,
            method=self.request.method,
            headers=_filter_dict(self.request.headers, pass_headers),
            **request_args
        )
        response = await fetcher().fetch(request)
        return response

    async def _filter_response(self, url, response):
        content_type = response.headers['Content-Type']
        if ';' in content_type:
            content_type = content_type.split(';')[0].lower()

        # API responseじゃなかったらlogして返す
        if not (self.request_api and content_type == 'application/json'):
            logger.warning('unknown request: %s %s', self.request_api, content_type)
            return response.body

        try:
            responseBody = json.loads(response.body)
            entities, result = normalize_mastodon_response(self.request_api, responseBody)
            await self._filter_entities(entities)
            denormalized = denormalize_mastodon_response(self.request_api, result, entities)
            return json.dumps(denormalized)
        except NotFound:
            return response.body

    def _filter_entities(self, entities):
        return _filter_entities(self.naumanni_app, entities)


async def _filter_entities(app, entities):
    for key in entities.keys():
        def _result_hook(result, kwargs):
            kwargs['objects'] = entities[key] = result
            return kwargs

        await app.emit_async(
            'filter-{}'.format(key),
            objects=entities[key], entities=entities,
            _result_hook=_result_hook)


def _filter_dict(src, keys):
    dst = {}
    for key in keys:
        if key in src:
            dst[key] = src[key]
    return dst
