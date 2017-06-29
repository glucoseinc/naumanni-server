# -*- coding: utf-8 -*-
import re

from ttp import ttp
from werkzeug import cached_property, unescape

tag_rex = re.compile('<(/?.*?)(\s+[^>]*)?/?>')


class JSONBasedModel(object):
    _defaults = {}

    def __init__(self, **kwargs):
        for key, val in self._defaults.items():
            setattr(self, key, val)
        for key, val in kwargs.items():
            setattr(self, key, val)

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}


class Account(JSONBasedModel):
    _defaults = {}


class Status(JSONBasedModel):
    _defaults = {
        'reblog': None
    }

    @cached_property
    def plainContent(self):
        # 雑なRemoveTag
        def handle_tag(m):
            tagname = m.group(1).lower()
            if tagname == '\p':
                return '\n\n'
            elif tagname == 'br':
                return '\n'
        return tag_rex.sub(handle_tag, self.content).rstrip()

    @cached_property
    def urls(self):
        parsed = ttp.Parser().parse(self.plainContent)
        return parsed.urls

    @property
    def urls_without_media(self):
        rv = []
        for url in self.urls:
            for media in self.media_attachments:
                if media.get('text_url', None) == url:
                    break
            else:
                rv.append(url)
        return rv

    def add_extended_attributes(self, key, data):
        if not hasattr(self, 'extended'):
            self.extended = {}
        self.extended[key] = data

    def get_extended_attributes(self, key, default=None):
        return getattr(self, 'extended', {}).get(key, default)


class Notification(JSONBasedModel):
    pass
