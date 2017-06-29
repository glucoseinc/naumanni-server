# -*- coding: utf-8 -*-

import json
import os
from weakref import ref as weakref

import pkg_resources


class Plugin(object):
    def __init__(self, app, module_name, plugin_id):
        self._app = weakref(app)
        self._module_name = module_name
        self._id = plugin_id

    @classmethod
    def from_ep(kls, app, ep):
        plugin_id = ep.name
        plugin_class = ep.load()

        return plugin_class(app, ep.module_name, plugin_id)

    @property
    def app_ref(self):
        return self._app

    @property
    def app(self):
        rv = self._app()
        if not rv:
            raise RuntimeError('Application went away')
        return rv

    @property
    def id(self):
        return self._id

    @property
    def js_package_name(self):
        package_json = pkg_resources.resource_string(self._module_name, 'package.json')
        if not package_json:
            return None
        package_json = json.loads(package_json)
        return package_json.get('name')

    @property
    def js_package_path(self):
        return os.path.dirname(self.path_if_exists('package.json'))

    @property
    def css_file_path(self):
        return self.path_if_exists('css/index.css')

    def path_if_exists(self, filename):
        fn = pkg_resources.resource_filename(self._module_name, filename)
        return fn if os.path.exists(fn) else None
