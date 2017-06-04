#!/usr/bin/env python
"""
TODO: http://docs.celeryproject.org/en/latest/userguide/extending.html#installing-bootsteps
      このテキストが関連あるか調べる
"""

import logging

from celery import Celery
from celery._state import connect_on_app_finalize

from naumanni.core import NaumanniApp


logger = logging.getLogger(__name__)


class NaumanniCelery(Celery):
    def __init__(self):
        super().__init__('naumanni')
        self.config_from_object('config')


@connect_on_app_finalize
def add_plugin_tasks(celeryapp):
    # TODO: debugはceleryappからとりたい
    NaumanniApp(debug=True)

    # TODO: cli_mainと被ってるけどどうすのがいいのかな
    logging.getLogger('tornado.curl_httpclient').setLevel(logging.INFO)
