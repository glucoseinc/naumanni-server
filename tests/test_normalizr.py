# -*- coding: utf-8 -*-
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


def test_normalize():
    source = {'id': 1, 'account': 'shn'}
    schema = account

    entities, result = normalize(source, schema)
    assert 'accounts' in entities
    assert entities['accounts'][1].account == 'shn'
    assert result == 1

    denormalized = denormalize(result, schema, entities)
    assert denormalized == source


def test_normalize_list_nested():
    source = [
        {
            'id': 100,
            'account': {
                'id': 1,
                'acct': 'shn'
            },
            'content': 'aaa',
            'reblog': {
                'id': 200,
                'account': {
                    'id': 2,
                    'acct': 'nayu'
                },
                'content': 'reblogged'
            }
        },
        {
            'id': 101,
            'account': {
                'id': 2,
                'acct': 'nayu'
            },
            'content': 'bbb',
            'reblog': None,
        },
        {
            'id': 102,
            'account': {
                'id': 1,
                'acct': 'shn'
            },
            'content': 'ccc',
            'reblog': None,
        },
    ]
    schema = [status]

    # test normalize
    entities, result = normalize(source, schema)
    assert 'accounts' in entities
    assert 'statuses' in entities
    assert len(entities['accounts']) == 2
    assert len(entities['statuses']) == 4
    assert entities['accounts'][1].acct == 'shn'
    assert entities['accounts'][2].acct == 'nayu'
    assert entities['statuses'][100].content == 'aaa'
    assert result == [100, 101, 102]

    # test denormalize
    denormalized = denormalize(result, schema, entities)
    print(denormalized)
    assert denormalized == source
