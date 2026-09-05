import hashlib
import json
from typing import Optional

from accord_api.modules import knowledge as context
from accord_api.modules.collaboration import handoffs as handoffs
from accord_api.modules.knowledge.schemas import Resource, ResourceEdit, SharedDocument
from accord_api.modules.permissions import policy as access
from accord_api.platform.commands import expect, operate, text
from accord_api.platform.db import database as store
from accord_api.platform.errors import DomainError


def publish(*, body: SharedDocument, uid):
    title = text(body.title)
    content = text(body.body)

    def run(db):
        aid = context.create_resource(db, uid, title, content, scope='team')
        db.execute(
            'INSERT INTO artifacts(id,unit_id,title,body,created_at,kind,author) VALUES(?,?,?,?,?,?,?)',
            (aid, uid, title, content, store.now(), 'note', uid),
        )
        return {'id': aid}

    return operate(uid, body, 'publish', run)


def resource_refs(db, uid, body):
    if not body.body.strip() and not body.resource_ids:
        raise DomainError(422, '请填写正文或选择资料。')
    refs = []
    for rid in dict.fromkeys(body.resource_ids):
        resource = access.resource_for(db, uid, rid)
        if body.scope == 'team' and resource['scope'] != 'team':
            raise DomainError(403, '团队资料集合只能引用已向团队共享的资料。')
        refs.append({'id': rid, 'version': resource['version']})
    return refs


def create_resource(*, body: Resource, uid):
    def run(db):
        refs = resource_refs(db, uid, body)
        rid = context.create_resource(
            db,
            uid,
            text(body.title),
            body.body.strip(),
            body.scope,
            'collection' if refs else 'note',
            refs=refs,
        )
        return {'id': rid, 'version': 1}

    return operate(uid, body, 'resource:create', run)


def update_resource(*, rid: str, body: ResourceEdit, uid):
    def run(db):
        resource = access.resource_for(db, uid, rid)
        if resource['owner_id'] != uid or resource['kind'] not in ('note', 'collection', 'memory'):
            raise DomainError(403, '这份资料需要通过所属工作流程更新。')
        expect(resource['version'], body.expected_version)
        if rid in body.resource_ids:
            raise DomainError(422, '资料不能引用自己。')
        refs = resource_refs(db, uid, body)
        version = resource['version'] + 1
        db.execute(
            'INSERT INTO accord_resource_versions VALUES(?,?,?,?,?,?,?)',
            (
                rid,
                version,
                text(body.title),
                body.body.strip(),
                json.dumps(refs),
                hashlib.sha256((body.body + json.dumps(refs, sort_keys=True)).encode()).hexdigest(),
                store.now(),
            ),
        )
        db.execute(
            'UPDATE accord_resources SET version=?,scope=?,kind=? WHERE id=?',
            (
                version,
                body.scope,
                'collection' if refs else 'memory' if resource['kind'] == 'memory' else 'note',
                rid,
            ),
        )
        return {'id': rid, 'version': version}

    return operate(uid, body, 'resource:update:' + rid, run)


def read_resource(*, rid: str, version: Optional[int] = None, uid):
    with store.lock:
        return context.public_resource(access.resource_for(store.connection(), uid, rid, version))
