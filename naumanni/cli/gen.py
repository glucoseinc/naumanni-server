# -*- coding: utf-8 -*-
import sys

import click


@click.group('gen')
def cli_gen():
    """`naumanni gen`の起点."""


@cli_gen.command('js')
@click.pass_context
def gen_js(ctx):
    """pluginのnaumanniフロントエンド用エントリポイントを生成する"""
    app = ctx.obj
    out = sys.stdout

    def _l(ln):
        out.write(ln + '\n')

    js_plugins = []
    for plugin in app.plugins.values():
        js_package_name = plugin.js_package_name
        if not js_package_name:
            continue

        kwds = {
            'plugin_id': plugin.id,
            'module': js_package_name,
        }
        js_plugins.append(kwds)

    # export default
    _l('export default {')
    for kwds in js_plugins:
        _l("""\t'{plugin_id}': require('{module}'),""".format(**kwds))
    _l('}')

    # export function loadPluginDefaultLocales()
    _l('export function loadPluginDefaultLocales() {')
    _l('\treturn [')
    for kwds in js_plugins:
        _l("""\t\trequire(/* webpackChunkName: 'locales/[request]' */ '{module}/locales/en'),""".format(**kwds))
    _l('\t]')
    _l('}')

    # export function loadPluginDefaultLocales()
    _l('export function loadPluginLocales(locale) {')
    _l('\treturn [')
    for kwds in js_plugins:
        _l(
            """\t\timport(/* webpackChunkName: 'locales/[request]' */ `{module}/locales/${{locale}}`),"""
            .format(**kwds)
        )
    _l('\t]')
    _l('}')


@cli_gen.command('yarn')
@click.pass_context
def gen_yarn(ctx):
    app = ctx.obj
    out = sys.stdout

    def _l(ln):
        out.write(ln + '\n')

    js_plugins = []
    for plugin in app.plugins.values():
        js_package_name = plugin.js_package_name
        js_package_path = plugin.js_package_path
        if not js_package_path:
            continue

        kwds = {
            'module': js_package_name,
            'module_path': js_package_path,
        }
        js_plugins.append(kwds)

    for kwds in js_plugins:
        _l("""yarn add file:{module_path}""".format(**kwds))


@cli_gen.command('css')
@click.pass_context
def gen_css(ctx):
    """pluginのnaumanniフロントエンド用CSSエントリポイントを生成する"""
    app = ctx.obj
    out = sys.stdout

    def _l(ln):
        out.write(ln + '\n')

    plugin_csss = []
    for plugin in app.plugins.values():
        css_file_path = plugin.css_file_path
        if not css_file_path:
            continue

        kwds = {
            'css_path': css_file_path,
        }
        plugin_csss.append(kwds)

    for kwds in plugin_csss:
        _l('@import "{css_path}";'.format(**kwds))
