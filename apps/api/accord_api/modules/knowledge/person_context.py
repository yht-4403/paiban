"""A person's four sources, filtered for the complete answer audience on every read."""

import hashlib
import json

from accord_api.modules.identity import service as identity
from accord_api.modules.permissions import policy as access
from accord_api.platform.errors import DomainError


def grant(db, owner, kind, sid):
    row = db.execute(
        'SELECT enabled,version FROM accord_context_grants WHERE owner_id=? AND source_kind=? AND source_id=?',
        (owner, kind, sid),
    ).fetchone()
    return dict(row) if row else {'enabled': 0, 'version': 0}


def shared(db, owner, kind, sid, audience):
    if any(not identity.shares_account_roster(owner, uid) for uid in audience):
        return False
    return all(uid == owner for uid in audience) or grant(db, owner, kind, sid)['enabled']


def source(db, owner, kind, sid, audience):
    if not audience or not all(
        db.execute('SELECT 1 FROM accord_accounts WHERE unit_id=?', (uid,)).fetchone()
        for uid in [owner, *audience]
    ):
        raise DomainError(404, '成员不存在。')
    if any(not identity.shares_account_roster(owner, uid) for uid in audience):
        raise DomainError(404, '上下文来源不存在。')
    if kind in ('document', 'memory'):
        doc = access.resource_for(db, audience[0], sid)
        if doc['owner_id'] != owner or not all(access.can_read(db, uid, doc) for uid in audience):
            raise DomainError(404, '资料不可见。')
        if doc['kind'] == 'collection':
            return None
        return {
            'title': doc['title'],
            'body': doc['body'][:4000],
            'version': doc['version'],
            'updated_at': doc['created_at'],
        }
    if kind == 'conversation':
        if not shared(db, owner, kind, sid, audience):
            raise DomainError(404, '会话未共享。')
        t = access.thread_for(owner, sid, db)
        if t['kind'] != 'workspace' or t['purpose'] != 'ordinary':
            raise DomainError(404, '仅可共享本人的普通工作会话。')
        if db.execute(
            'SELECT 1 FROM accord_thread_archives WHERE owner_id=? AND thread_id=?', (owner, sid)
        ).fetchone():
            raise DomainError(404, '会话已移除。')
        lines = []
        for m in reversed(
            db.execute(
                "SELECT id,body,from_kind,meta,sources FROM messages WHERE conversation_id=? AND from_kind IN ('human','agent') ORDER BY rowid DESC LIMIT 12",
                (sid,),
            ).fetchall()
        ):
            if m['from_kind'] == 'agent' and json.loads(m['meta']).get('status') != 'done':
                continue
            try:
                from accord_api.modules.knowledge.retrieval import check_message

                check_message(db, m, audience)
                for rid in json.loads(m['sources']):
                    doc = access.resource_for(db, owner, rid)
                    if not all(access.can_read(db, uid, doc) for uid in audience):
                        raise DomainError(404, '引用未共享。')
            except DomainError:
                continue
            lines.append(
                ('本人：' if m['from_kind'] == 'human' else 'Agent 草稿：') + m['body'][:1200]
            )
        return {
            'title': t['title'],
            'body': '\n'.join(lines)[-5000:],
            'version': grant(db, owner, kind, sid)['version'],
            'updated_at': t['updated_at'],
        }
    if kind == 'state':
        if not shared(db, owner, kind, owner, audience):
            raise DomainError(404, '状态未共享。')
        tasks = [
            dict(r)
            for r in db.execute(
                """SELECT t.id,t.title,t.status,t.updated_at,a.creator_id FROM tasks t
                JOIN accord_task_acl a ON a.task_id=t.id WHERE t.assignee_id=?
                ORDER BY t.updated_at DESC LIMIT 12""",
                (owner,),
            )
            if identity.shares_account_roster(owner, r['creator_id'])
        ]
        meetings = []
        for r in db.execute(
            """SELECT id,owner_id,title,status,member_ids,updated_at FROM accord_flows
            WHERE kind IN ('sync','decision') ORDER BY updated_at DESC LIMIT 12"""
        ):
            members = json.loads(r['member_ids'])
            if owner in members and all(
                identity.shares_account_roster(r['owner_id'], member) for member in members
            ):
                meetings.append({k: r[k] for k in ('id', 'title', 'status', 'updated_at')})
        return {
            'title': '待办与会议状态',
            'body': json.dumps({'tasks': tasks, 'meetings': meetings}, ensure_ascii=False),
            'version': grant(db, owner, kind, owner)['version'],
            'updated_at': max([r['updated_at'] for r in tasks + meetings], default=''),
        }
    raise DomainError(404, '上下文来源不存在。')


def collect(
    db,
    owner,
    audience,
    query='',
    *,
    exclude_thread='',
    resource_versions=None,
    source_ids=None,
):
    from accord_api.modules.knowledge import retrieval

    result = retrieval.search(
        db,
        owner,
        audience,
        query,
        exclude_thread=exclude_thread,
        resource_versions=resource_versions,
        source_ids=source_ids,
    )
    # Broad people questions also need recent work; keep these labeled as background.
    if query and len(result['sources']) < 8:
        recent = retrieval.search(
            db,
            owner,
            audience,
            '',
            exclude_thread=exclude_thread,
            resource_versions=resource_versions,
            source_ids=source_ids,
        )
        seen = {r['chunk_id'] for r in result['sources']}
        for ref in recent['sources']:
            if ref['chunk_id'] not in seen and len(result['sources']) < 8:
                ref['retrieval_reason'] = '近期背景，未必与问题直接相关'
                result['sources'].append(ref)
        result['has_more'] = result['has_more'] or recent['has_more']
    # Tasks/meetings retain their explicit owner sharing control and live status.
    # An explicit resource boundary deliberately excludes all live state and old context.
    if source_ids:
        return {'person_id': owner, **result}
    try:
        item = source(db, owner, 'state', owner, audience)
        item.update(source_kind='state', id=owner, owner_id=owner)
        item['digest'] = hashlib.sha256(item['body'].encode()).hexdigest()
        result['sources'].append(item)
    except DomainError:
        pass
    return {'person_id': owner, **result}


def validate(db, sources, audience, strict=True):
    for ref in sources:
        if ref.get('chunk_id'):
            from accord_api.modules.knowledge import retrieval

            retrieval.validate(db, [ref], audience, strict)
            continue
        current = source(db, ref['owner_id'], ref['source_kind'], ref['id'], audience)
        if not current or (strict and current['version'] != ref['version']):
            raise DomainError(409, '上下文版本或共享范围已改变，请重新收集。')
        # State is intentionally live; a completed task must not invalidate past minutes.
        if (
            strict
            and ref['source_kind'] != 'state'
            and hashlib.sha256(current['body'].encode()).hexdigest() != ref['digest']
        ):
            raise DomainError(409, '上下文已更新，请重新收集。')
