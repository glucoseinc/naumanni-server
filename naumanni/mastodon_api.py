# -*- coding:utf-8 -*-
from werkzeug import routing

from naumanni.mastodon_models import Account, Notification, Status
from naumanni.normalizr import denormalize, Entity, normalize


account = Entity('accounts', Account)
status = Entity('statuses', Status, {
    'account': account,
    'reblog': Entity('statuses', Status)
})
notification = Entity('notifications', Notification, {
    'account': account,
    'status': status,
})


# api map
apiSchemaMap = routing.Map()
apiSchemaMapAdapter = None
schemaFuncs = {}


def get_adapter():
    global apiSchemaMapAdapter
    if not apiSchemaMapAdapter:
        apiSchemaMapAdapter = apiSchemaMap.bind('mastodon', '/')
    return apiSchemaMapAdapter


def get_schema(api):
    adapter = get_adapter()
    endpoint, args = adapter.match(api)
    schema = schemaFuncs[endpoint](**args)
    return schema


def normalize_mastodon_response(api, inputData):
    return normalize(inputData, get_schema(api))


def denormalize_mastodon_response(api, inputData, entities):
    return denormalize(inputData, get_schema(api), entities)


def register_schema(rule, **options):
    def decorator(f):
        global apiSchemaMapAdapter
        endpoint = options.pop('endpoint', f.__name__)

        apiSchemaMap.add(
            routing.Rule(rule, endpoint=endpoint, **options)
        )
        schemaFuncs[endpoint] = f
        apiSchemaMapAdapter = None  # reset
        return f
    return decorator


@register_schema('/accounts/verify_credentials')
def accounts_verify_credentials():
    return account


@register_schema('/timelines/home', endpoint='timeline')
@register_schema('/timelines/public', endpoint='timeline')
@register_schema('/timelines/tag/<hashtag>', endpoint='timeline')
@register_schema('/accounts/<user_id>/statuses', endpoint='timeline')
def timeline(hashtag=None, user_id=None):
    return [status]


@register_schema('/__websocket__/update')
def websocket_update():
    return status


@register_schema('/__websocket__/notification')
def websocket_notification():
    return notification
