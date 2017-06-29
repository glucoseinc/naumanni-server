# -*- coding: utf-8 -*-

"""CLI Main."""

from itertools import groupby
import logging
import os
import re
import sys

# community module
import click
from click.core import Context

import naumanni
from naumanni.core import NaumanniApp
from ..logging_utils import LOG_COLORED, set_nice_record_factory


# project module
logger = logging.getLogger(__name__)


@click.group()
@click.option('--debug', is_flag=True)
@click.pass_context
def cli_main(ctx, debug):
    """`crcr`の起点.

    :param Context ctx: Context
    """
    # initialize console logging
    _init_logging(debug)

    ctx.obj = NaumanniApp(debug=debug)


def _init_logging(debug=False):
    # if we are attached to tty, use colorful.
    set_nice_record_factory()

    fh = logging.StreamHandler(sys.stderr)
    fmt = '[%(levelname4)s] %(name)-28s time:%(asctime)s pid:%(pid)-5d  %(message)s'
    if sys.stderr.isatty() and LOG_COLORED:
        # ttyだったら色をつけちゃえ
        # 色指示子で9charsとる
        fmt = '[%(nice_levelname4)-13s] %(nice_name)-40s time:%(asctime)s pid:%(pid)-5d  %(message)s'
    fh.setFormatter(logging.Formatter(fmt))

    root_logger = logging.getLogger()
    root_logger.addHandler(fh)
    # root_logger.setLevel(logging.DEBUG if debug else logging.INFO)
    root_logger.setLevel(logging.DEBUG)

    logging.getLogger('tornado.curl_httpclient').setLevel(logging.INFO)


@cli_main.command('webserver')
@click.pass_context
def cli_main_run_webserver(ctx):
    """
    run Naumanni's Websocket server
    """
    app = ctx.obj

    import tornado.httpclient
    tornado.httpclient.AsyncHTTPClient.configure("tornado.curl_httpclient.CurlAsyncHTTPClient")

    # start server
    if app.debug:
        from naumanni.web.server import DebugWebServer
        webserver_class = DebugWebServer
    else:
        from naumanni.web.fork_server import ForkWebServer
        webserver_class = ForkWebServer

    app.webserver = webserver_class(app, app.config.listen)
    app.webserver.start()
