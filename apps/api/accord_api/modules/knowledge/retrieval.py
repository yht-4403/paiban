"""Permission checked search and evidence, shared by chat tools and HTTP reads."""

import json

from accord_api.modules.knowledge import index
from accord_api.modules.permissions import policy as access
from accord_api.platform.errors import DomainError


def check_message(db, message, audience, seen=None):
    """Re-check transitive evidence; stored answer text never becomes a new permission grant."""
    seen = set(seen or ())
    if message['id'] in seen or len(seen) >= 12:
        raise DomainError(403, '上下文引用链不可用。')
    seen.add(message['id'])
    for rid in json.loads(message['sources']):
        doc = access.resource_for(db, audience[0], rid)
        if not all(access.can_read(db, uid, doc) for uid in audience):
            raise DomainError(403, '引用资料已收回。')
    from accord_api.modules.knowledge import person_context

    for ref in json.loads(message['meta']).get('context_sources', []):
        if ref.get('chunk_id'):
            read(db, ref['chunk_id'], audience, seen=seen)
        else:
            person_context.validate(db, [ref], audience, strict=False)


def read(db, cid, audience, *, seen=None):
    if not audience or not all(
        db.execute('SELECT 1 FROM accord_accounts WHERE unit_id=?', (u,)).fetchone()
        for u in audience
    ):
        raise DomainError(404, '内容不可用。')
    chunk = db.execute('SELECT * FROM accord_content_chunks WHERE id=?', (cid,)).fetchone()
    if not chunk:
        raise DomainError(404, '内容不存在或已更新。')
    from accord_api.modules.knowledge import person_context

    owner, sid, kind = chunk['owner_id'], chunk['source_id'], chunk['source_kind']
    if not db.execute('SELECT 1 FROM accord_accounts WHERE unit_id=?', (owner,)).fetchone():
        raise DomainError(404, '成员不存在。')
    grant_version = 0
    if kind == 'conversation':
        if not person_context.shared(db, owner, kind, sid, audience):
            raise DomainError(404, '会话未共享。')
        thread = access.thread_for(owner, sid, db)
        if (
            thread['owner_id'] != owner
            or thread['kind'] != 'workspace'
            or thread['purpose'] != 'ordinary'
        ):
            raise DomainError(404, '会话不在可用范围。')
        if db.execute(
            'SELECT 1 FROM accord_thread_archives WHERE owner_id=? AND thread_id=?', (owner, sid)
        ).fetchone():
            raise DomainError(404, '会话已移除。')
        message = db.execute(
            'SELECT * FROM messages WHERE id=? AND conversation_id=?', (chunk['message_id'], sid)
        ).fetchone()
        if (
            not message
            or message['from_kind'] not in ('human', 'agent')
            or (
                message['from_kind'] == 'agent'
                and json.loads(message['meta']).get('status') != 'done'
            )
        ):
            raise DomainError(404, '消息不可用。')
        check_message(db, message, audience, seen)
        body, title = message['body'], thread['title']
        label = '本人记录' if message['from_kind'] == 'human' else 'Agent 草稿'
        grant_version = person_context.grant(db, owner, kind, sid)['version']
    else:
        doc = access.resource_for(db, audience[0], sid, chunk['version'])
        if doc['owner_id'] != owner or not all(access.can_read(db, u, doc) for u in audience):
            raise DomainError(404, '资料不可见。')
        body, title, label = doc['body'], doc['title'], '资料' if kind == 'document' else '记忆'
    excerpt = body[chunk['offset'] : chunk['offset'] + len(chunk['body'])]
    if index.digest(excerpt) != chunk['digest']:
        raise DomainError(409, '内容已更新，请重新检索。')
    return dict(
        chunk_id=cid,
        id=sid,
        owner_id=owner,
        source_kind=kind,
        message_id=chunk['message_id'],
        title=title,
        body=excerpt,
        label=label,
        version=chunk['version'],
        offset=chunk['offset'],
        digest=chunk['digest'],
        grant_version=grant_version,
        updated_at=chunk['updated_at'],
    )


def validate(db, refs, audience, strict=True):
    for ref in refs:
        current = read(db, ref['chunk_id'], audience)
        if strict and (
            current['digest'] != ref['digest']
            or current['grant_version'] != ref.get('grant_version', 0)
        ):
            raise DomainError(409, '上下文已更新，请重新检索。')


def search(
    db,
    owner,
    audience,
    query,
    *,
    limit=8,
    exclude_thread='',
    resource_versions=None,
    source_ids=None,
):
    pending = index.synchronize(db)
    selected = frozenset(source_ids or ())
    words = index.tokens(query)[:32]
    params = [owner]
    if words:
        # Terms are generated locally and quoted; arbitrary FTS syntax is never accepted.
        sql = """SELECT c.* FROM accord_content_fts f JOIN accord_content_chunks c ON c.id=f.chunk_id
          WHERE c.owner_id=? AND c.active=1 AND accord_content_fts MATCH ? ORDER BY rank"""
        params.append(' OR '.join('"' + word + '"' for word in words))
    else:
        sql = 'SELECT c.* FROM accord_content_chunks c WHERE c.owner_id=? AND c.active=1 ORDER BY c.updated_at DESC'
    hits, scanned, more = [], 0, False
    for chunk in db.execute(sql, params):
        if selected and chunk['source_id'] not in selected:
            continue
        if chunk['source_kind'] == 'conversation' and chunk['source_id'] == exclude_thread:
            continue
        if (
            chunk['source_kind'] != 'conversation'
            and resource_versions is not None
            and resource_versions.get(chunk['source_id']) != chunk['version']
        ):
            continue
        # Permission checks occur before any title, text, or result count leaves this service.
        scanned += 1
        if scanned > 1000:
            more = True
            break
        try:
            hit = read(db, chunk['id'], audience)
        except DomainError:
            continue
        if len(hits) == limit:
            more = True
            break
        hits.append(hit)
    return {
        'sources': hits,
        'has_more': more,
        'index_pending': bool(pending),
        'coverage': (
            '只检索本轮指定资料；摘录不是全部内容。'
            if selected
            else '按关键词检索获准资料与历史会话；摘录不是全部内容，Agent 草稿不代表本人决定。'
        ),
    }


def public_ref(ref):
    return {k: v for k, v in ref.items() if k != 'body'}
