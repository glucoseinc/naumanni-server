# -*- coding: utf-8 -*-

"""WebUI."""


def create_webapp(naumanni, **kwargs):
    """App factory.

    :param CircleCore core: CircleCore Core
    :param str base_url: ベースURL
    :param int ws_port: Websocket Port Number
    :return: WebUI App
    :rtype: CCWebApp
    """
    from .app import NaumanniWebApp
    app = NaumanniWebApp(naumanni, **kwargs)
    return app
