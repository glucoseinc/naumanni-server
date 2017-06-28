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
    fh = logging.StreamHandler(sys.stderr)
    set_default_formatter = True
    if sys.stderr.isatty():
        try:
            from ..logger import NiceColoredFormatter
            # 色指示子で9charsとる
            fh.setFormatter(NiceColoredFormatter(
                '%(nice_levelname)-14s %(nice_name)-33s: %(message)s',
            ))
            set_default_formatter = False
        except ImportError:
            pass
    if set_default_formatter:
        fh.setFormatter(logging.Formatter(
            '%(levelname)-5s %(name)-24s: %(message)s',
        ))

    root_logger = logging.getLogger()
    root_logger.addHandler(fh)
    root_logger.setLevel(logging.DEBUG if debug else logging.INFO)

    logging.getLogger('tornado.curl_httpclient').setLevel(logging.INFO)


@cli_main.command('webserver')
@click.pass_context
def cli_main_run_webserver(ctx):
    """
    run Naumanni's Websocket server
    """
    app = ctx.obj

    logger.info('Master process PID:%s', os.getpid())

    import tornado.httpclient
    tornado.httpclient.AsyncHTTPClient.configure("tornado.curl_httpclient.CurlAsyncHTTPClient")

    # start server
    if app.debug:
        from naumanni.web.server import DebugWebServer
        webserver = DebugWebServer
    else:
        from naumanni.web.fork_server import ForkWebServer
        webserver = ForkWebServer

    webserver(app, app.config.listen).start()
