import hashlib
import json

from accord_api.modules.permissions import policy as access
from accord_api.platform.db import database as store


def create_resource(
    db, uid, title, body, scope='private', kind='note', round_id='', refs=None, resource_id=None
):
    rid = resource_id or store.new_id('resource')
    now = store.now()
    refs = refs or []
    db.execute(
        'INSERT INTO accord_resources(id,owner_id,kind,scope,round_id,created_at) VALUES(?,?,?,?,?,?)',
        (rid, uid, kind, scope, round_id, now),
    )
    db.execute(
        'INSERT INTO accord_resource_versions(resource_id,version,title,body,refs,digest,created_at) VALUES(?,1,?,?,?,?,?)',
        (
            rid,
            title,
            body,
            json.dumps(refs),
            hashlib.sha256((body + json.dumps(refs, sort_keys=True)).encode()).hexdigest(),
            now,
        ),
    )
    return rid


def public_resource(resource, include_body=True):
    fields = ('id', 'unit_id', 'kind', 'scope', 'round_id', 'version', 'title', 'created_at')
    result = {key: resource[key] for key in fields}
    result['refs'] = json.loads(resource['refs'])
    if include_body:
        result['body'] = resource['body']
    return result


def available(db, uid, thread=None, include_body=True):
    result = []
    for row in db.execute(
        'SELECT * FROM accord_resources WHERE active=1 ORDER BY created_at DESC'
    ).fetchall():
        if access.can_read(db, uid, row) and (not thread or access.compatible(db, thread, row)):
            result.append(public_resource(access.resource_for(db, uid, row['id']), include_body))
    return result
