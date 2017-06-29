# -*- coding:utf-8 -*-
from naumanni.web.proxy import (
    https_prefix_rex, mastodon_api_rex,
)


def test_rex():
    """使っている正規表現のテスト"""
    mo = https_prefix_rex.match('http://')
    assert mo
    mo = https_prefix_rex.match('https://')
    assert mo
    mo = https_prefix_rex.match('http:/')
    assert mo
    mo = https_prefix_rex.match('https:/')
    assert mo

    mo = mastodon_api_rex.match('https://friends.nico/api/v1/accounts/verify_credentials')
    assert mo.groups() == ('friends.nico', '/accounts/verify_credentials')

    mo = mastodon_api_rex.match('https://friends.nico/api/v1/accounts/verify_credentials?hogehoge')
    assert mo.groups() == ('friends.nico', '/accounts/verify_credentials')
