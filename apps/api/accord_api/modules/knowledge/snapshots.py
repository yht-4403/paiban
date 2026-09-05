import hashlib
import json

from accord_api.modules.collaboration.schemas import readable_attachment
from accord_api.modules.knowledge.bindings import effective, expand
from accord_api.modules.knowledge.resources import available
from accord_api.modules.permissions import policy as access
from accord_api.platform.errors import DomainError


def manifest(db, uid, tid, user_mid, extra_ids=None):
    thread = access.thread_for(uid, tid, db)
    sources = effective(db, uid, thread)
    references = [{'id': r['id'], 'version': r['version']} for r in sources['resources']]
    references += [
        {'id': rid} for rid in (extra_ids or []) if rid not in {r['id'] for r in references}
    ]
    # A folder or explicit selection narrows the scope, including an empty folder.
    automatic = (
        thread['purpose'] == 'ordinary'
        and not references
        and not thread['folder_id']
        and not sources['binding']['folder_ids']
    )
    if automatic:
        resources = [
            {key: r[key] for key in ('id', 'version', 'title')}
            for r in available(db, uid, thread, False)
            if r['id'] not in sources['binding']['excluded']
        ]
        if len(resources) > 200 or len(json.dumps(resources, ensure_ascii=False)) > 24000:
            raise DomainError(422, '可用资料较多，请指定文件夹或资料后发送。')
    else:
        resources = expand(db, uid, thread, references)
    cutoff = db.execute(
        'SELECT rowid FROM messages WHERE id=? AND conversation_id=?', (user_mid, tid)
    ).fetchone()[0]
    floor = access.message_floor(db, thread)
    rows = db.execute(
        'SELECT id,from_kind,body,meta,sources FROM messages WHERE conversation_id=? AND rowid<? AND rowid>=? ORDER BY rowid DESC LIMIT 40',
        (tid, cutoff, floor),
    ).fetchall()
    history, history_sources, budget = [], [], 16000
    for item in rows:
        if item['from_kind'] not in ('human', 'agent') or (
            item['from_kind'] == 'agent' and json.loads(item['meta']).get('status') != 'done'
        ):
            continue
        from accord_api.modules.knowledge.retrieval import check_message

        check_message(db, item, access.participants(thread))
        if len(item['body']) > budget:
            break
        history.append(item['id'])
        history_sources.extend(json.loads(item['sources']))
        budget -= len(item['body'])
        if len(history) >= 20:
            break
    message_ids = [user_mid, *history]
    attachment_budget = 64000
    attachments = []
    if message_ids:
        placeholders = ','.join('?' for _ in message_ids)
        for item in db.execute(
            f"""SELECT * FROM accord_thread_attachments
                WHERE thread_id=? AND owner_id=? AND message_id IN ({placeholders})
                ORDER BY created_at DESC,rowid DESC""",
            (tid, uid, *message_ids),
        ):
            if not readable_attachment(item['filename'], item['mime_type']):
                continue
            if len(item['content']) > attachment_budget:
                continue
            attachments.append(
                {
                    key: item[key]
                    for key in ('id', 'message_id', 'filename', 'content', 'mime_type', 'digest')
                }
            )
            attachment_budget -= len(item['content'])
    result = {
        'thread_id': tid,
        'actor_id': uid,
        'purpose': thread['purpose'],
        'round_id': thread['round_id'],
        'audience': access.participants(thread),
        'history_floor': floor,
        'selection_mode': 'automatic' if automatic else 'selected',
        'resources': resources,
        'roots': references,
        'history_ids': list(reversed(history)),
        'history_sources': list(dict.fromkeys(history_sources)),
        'message_cutoff': cutoff,
        'user_message_id': user_mid,
        'attachments': list(reversed(attachments)),
        'binding_version': sources['binding']['version'],
        'folder_id': sources['folder_id'],
        'folder_version': sources['folder_version'],
    }
    validate(db, result)
    return result


def validate(db, manifest_):
    if not db.execute(
        'SELECT 1 FROM accord_accounts WHERE unit_id=?', (manifest_['actor_id'],)
    ).fetchone():
        raise DomainError(403, '当前账号已无权继续这次回答。')
    thread = access.thread_for(manifest_['actor_id'], manifest_['thread_id'], db)
    if (
        thread['purpose'] != manifest_['purpose']
        or access.participants(thread) != manifest_['audience']
        or thread['status'] != 'agent'
    ):
        raise DomainError(409, '协作范围已改变，请重新开始这次回答。')
    if manifest_.get('history_floor', 0) != access.message_floor(db, thread):
        raise DomainError(409, '群成员与历史范围已改变，请重新提问。')
    for ref in manifest_['resources']:
        resource = access.resource_for(db, manifest_['actor_id'], ref['id'], ref['version'])
        if not access.compatible(db, thread, resource):
            raise DomainError(403, '资料权限已改变，已停止使用这些内容。')
    for rid in manifest_.get('history_sources', []):
        resource = access.resource_for(db, manifest_['actor_id'], rid)
        if not access.compatible(db, thread, resource):
            raise DomainError(403, '历史消息的资料权限已改变，请以获准资料新建聊天。')
    allowed_messages = {manifest_['user_message_id'], *manifest_.get('history_ids', [])}
    for item in manifest_.get('attachments', []):
        current = db.execute(
            """SELECT * FROM accord_thread_attachments
               WHERE id=? AND thread_id=? AND owner_id=?""",
            (item['id'], manifest_['thread_id'], manifest_['actor_id']),
        ).fetchone()
        if (
            not current
            or current['message_id'] not in allowed_messages
            or current['message_id'] != item['message_id']
            or current['filename'] != item['filename']
            or current['mime_type'] != item['mime_type']
            or current['digest'] != item['digest']
            or hashlib.sha256(current['content'].encode()).hexdigest() != item['digest']
        ):
            raise DomainError(409, '会话附件已改变，请重新发送。')
    from accord_api.modules.knowledge import person_context

    person_context.validate(db, manifest_.get('context_sources', []), manifest_['audience'])
    from accord_api.modules.knowledge.retrieval import check_message

    for mid in manifest_.get('history_ids', []):
        message = db.execute('SELECT * FROM messages WHERE id=?', (mid,)).fetchone()
        if not message:
            raise DomainError(409, '历史消息已改变。')
        check_message(db, message, manifest_['audience'])
    return thread


def history(db, manifest_):
    result = []
    for mid in manifest_['history_ids']:
        row = db.execute(
            'SELECT from_kind,from_unit,body,meta FROM messages WHERE id=?', (mid,)
        ).fetchone()
        if row:
            item = {
                'role': 'user' if row['from_kind'] == 'human' else 'assistant',
                'content': row['body'],
            }
            if manifest_.get('is_group'):
                sender = db.execute(
                    'SELECT person_name FROM units WHERE id=?', (row['from_unit'],)
                ).fetchone()
                item['content'] = (
                    '['
                    + (sender['person_name'] if sender else '成员')
                    + ('的 Agent' if row['from_kind'] == 'agent' else '')
                    + '] '
                    + item['content']
                )
            if item['role'] == 'assistant':
                run_id = json.loads(row['meta']).get('run_id')
                run = db.execute(
                    'SELECT reasoning_content FROM accord_runs WHERE id=? AND assistant_message_id=?',
                    (run_id, mid),
                ).fetchone()
                item['reasoning_content'] = run['reasoning_content'] if run else ''
            result.append(item)
    return result
