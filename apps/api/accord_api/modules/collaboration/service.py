import json
from datetime import datetime, timezone

from accord_api.modules import knowledge as context
from accord_api.modules.agent_runs import service as runtime
from accord_api.modules.collaboration import attachments
from accord_api.modules.collaboration import repository as collaboration_repository
from accord_api.modules.collaboration.repository import message as _message
from accord_api.modules.collaboration.schemas import (
    Confirmation,
    Handoff,
    Message,
    NewThread,
    OpenChat,
    TaskDelete,
    TaskStatus,
)
from accord_api.modules.identity import repository as identity_repository
from accord_api.modules.identity import service as identity
from accord_api.modules.permissions import policy as access
from accord_api.modules.permissions.policy import thread_for
from accord_api.modules.workspace import service as workspace
from accord_api.platform.commands import operate, text
from accord_api.platform.db import database as store
from accord_api.platform.errors import DomainError


def new_thread(*, body: NewThread, uid):
    if not identity_repository.get_unit(body.target_id) or not identity.shares_account_roster(
        uid, body.target_id
    ):
        raise DomainError(404, '成员不存在。')

    def run(db):
        if body.folder_id:
            workspace.folder_for(db, uid, body.folder_id)
        tid = store.new_id('thread')
        now = store.now()
        db.execute(
            'INSERT INTO accord_threads(id,owner_id,target_id,title,kind,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
            (
                tid,
                uid,
                body.target_id,
                text(body.title),
                'workspace' if body.target_id == uid else 'peer',
                now,
                now,
            ),
        )
        if body.folder_id:
            db.execute('INSERT INTO accord_placements VALUES(?,?,?,1)', (uid, tid, body.folder_id))
        if body.source_ids:
            current = thread_for(uid, tid, db)
            for resource_id in body.source_ids:
                resource = access.resource_for(db, uid, resource_id)
                if not access.compatible(db, current, resource):
                    raise DomainError(403, '这份资料不适用于当前协作范围。')
            context.put_binding(db, uid, 'thread', tid, body.source_ids, [], 1)
        return {'id': tid}

    return operate(uid, body, 'create_thread', run)


def thread(*, tid: str, person_history: bool = False, uid):
    with store.lock:
        db = store.connection()
        row = thread_for(uid, tid, db)
        segments = (
            pair_threads(db, uid, row['target_id'] if row['owner_id'] == uid else row['owner_id'])
            if person_history and row['kind'] == 'peer'
            else [row]
        )
        messages = []
        tool_calls = []
        for segment in segments:
            floor = access.message_floor(db, segment, uid)
            messages.extend(
                collaboration_repository.row_msg(r, uid, db)
                for r in db.execute(
                    'SELECT * FROM messages WHERE conversation_id=? AND rowid>=? ORDER BY created_at,rowid',
                    (segment['id'], floor),
                )
            )
            tool_calls.extend(
                dict(r)
                for r in db.execute(
                    'SELECT c.*,r.assistant_message_id FROM accord_tool_calls c JOIN accord_runs r ON r.id=c.run_id WHERE r.thread_id=? AND r.assistant_message_id IN (SELECT id FROM messages WHERE rowid>=?) ORDER BY c.created_at,c.rowid',
                    (segment['id'], floor),
                )
            )
        messages.sort(key=lambda message: message['created_at'])
        inputs = {
            r['run_id']: json.loads(r['manifest'])
            for r in db.execute(
                """SELECT i.* FROM accord_run_inputs i JOIN accord_runs r ON r.id=i.run_id
            WHERE r.thread_id=? AND r.status IN ('queued','running')""",
                (tid,),
            )
        }
        return {
            'thread': row,
            'messages': messages,
            'attachments': attachments.public_rows(
                db, uid, [segment['id'] for segment in segments]
            ),
            'tool_calls': tool_calls,
            'segments': segments,
            'context': {
                **context.effective(db, uid, row),
                'available': context.available(db, uid, row, False),
            },
            'active_context': [
                {
                    k: m[k]
                    for k in (
                        'resources',
                        'roots',
                        'binding_version',
                        'folder_id',
                        'folder_version',
                    )
                    if k in m
                }
                for m in inputs.values()
            ],
        }


def send_message(*, tid: str, body: Message, uid):
    message_attachments = getattr(body, 'attachments', [])
    content = body.body.strip()
    if not content and not message_attachments:
        raise DomainError(422, '消息或附件不能为空。')

    def run(db):
        current = thread_for(uid, tid, db)
        if current['kind'] == 'group':
            raise DomainError(422, '请使用群聊消息入口。')
        if current['status'] == 'closed':
            raise DomainError(409, '本轮已结束，请开始新的事项。')
        if current['status'] == 'scheduled':
            raise DomainError(409, '这条协作尚未送达，草稿可以保留，送达后继续发送。')
        for resource_id in body.source_ids:
            resource = access.resource_for(db, uid, resource_id)
            if not access.compatible(db, current, resource):
                raise DomainError(404, '引用资料不存在或不可共享。')
        if db.execute(
            "SELECT 1 FROM accord_flows WHERE kind='task_summary' AND thread_id=? AND status IN ('queued','running','needs_input')",
            (tid,),
        ).fetchone():
            raise DomainError(409, '待办正在整理，请补充进展或取消整理后继续。')
        if runtime.active(db, tid):
            raise DomainError(409, '回答仍在生成，可以先停止。')
        if body.source_ids and current['status'] == 'agent':
            current_binding = context.binding(db, uid, 'thread', tid)
            context.put_binding(
                db,
                uid,
                'thread',
                tid,
                current_binding['included'] + body.source_ids,
                [rid for rid in current_binding['excluded'] if rid not in body.source_ids],
                current_binding['version'] + 1,
            )
        if uid == current['target_id'] and current['status'] == 'waiting':
            _message(db, tid, 'system', uid, '本人开始回复，Agent 暂停代答。')
        mid = _message(db, tid, 'human', uid, content, body.source_ids)
        attachment_ids = attachments.save(db, uid, current, mid, message_attachments)
        if attachment_ids:
            message = db.execute('SELECT meta FROM messages WHERE id=?', (mid,)).fetchone()
            meta = json.loads(message['meta'])
            meta['attachment_ids'] = attachment_ids
            db.execute('UPDATE messages SET meta=? WHERE id=?', (json.dumps(meta), mid))
        rid = None
        if current['status'] == 'agent':
            assistant_mid = _message(db, tid, 'agent', current['target_id'], '')
            rid = runtime.enqueue(db, tid, uid, mid, assistant_mid, body.source_ids)
        if uid == current['target_id'] and current['status'] == 'waiting':
            db.execute("UPDATE accord_threads SET status='human' WHERE id=?", (tid,))
        title_source = content or message_attachments[0].filename
        title = title_source[:40] if current['title'] == '新的协作' else current['title']
        db.execute(
            'UPDATE accord_threads SET title=?,updated_at=? WHERE id=?', (title, store.now(), tid)
        )
        return {'id': mid, 'run_id': rid}

    return operate(uid, body, 'message:' + tid, run)


def _handoff_brief(db, thread, note):
    """Build a bounded brief from the actual work item instead of forwarding only a note."""
    rows = db.execute(
        """SELECT from_kind,from_unit,body,meta FROM messages
        WHERE conversation_id=? AND from_kind IN ('human','agent') AND trim(body)!=''
        ORDER BY rowid""",
        (thread['id'],),
    ).fetchall()
    requester = [row['body'].strip() for row in rows if row['from_kind'] == 'human' and row['from_unit'] == thread['owner_id']]
    answers = [
        row['body'].strip()
        for row in rows
        if row['from_kind'] == 'agent'
        and row['from_unit'] == thread['target_id']
        and json.loads(row['meta']).get('status') == 'done'
    ]

    def compact(value, limit):
        value = ' '.join(value.split())
        return value if len(value) <= limit else value[: limit - 1].rstrip() + '…'

    parts = []
    if requester:
        parts.append('需要处理：' + compact(requester[-1], 420))
    if answers:
        parts.append('Agent 已整理：' + compact(answers[-1], 720))
    if note.strip():
        parts.append('发起人补充：' + compact(note, 420))
    return '\n'.join(parts)


def handoff(*, tid: str, body: Handoff, uid):
    def run(db):
        row = thread_for(uid, tid, db)
        if row['purpose'] != 'ordinary':
            raise DomainError(403, '请使用课题内的提交或交接操作。')
        if row['owner_id'] != uid or row['kind'] != 'peer':
            raise DomainError(403, '只有发起人可以找对方本人。')
        if row['status'] != 'agent':
            raise DomainError(409, '这条请求已经提交给本人。')
        if db.execute(
            "SELECT 1 FROM accord_flows WHERE kind='task_summary' AND thread_id=? AND status IN ('queued','running','needs_input')",
            (tid,),
        ).fetchone():
            raise DomainError(409, '待办正在整理，请补充进展或取消整理后继续。')
        if runtime.active(db, tid):
            raise DomainError(409, '请等待 Agent 完整回答后再找本人。')
        if not db.execute('SELECT 1 FROM messages WHERE conversation_id=?', (tid,)).fetchone():
            raise DomainError(422, '先说明需要对方处理的事情。')
        if not runtime.has_complete_answer(db, tid, row['target_id']):
            raise DomainError(409, 'Agent 尚未完整回答，请重试或继续提问。')
        references = []
        for message in db.execute(
            'SELECT sources,meta FROM messages WHERE conversation_id=?', (tid,)
        ):
            from accord_api.modules.knowledge import person_context

            person_context.validate(
                db,
                json.loads(message['meta']).get('context_sources', []),
                access.participants(row),
                strict=False,
            )
            citations = {ref['id']: ref for ref in json.loads(message['meta']).get('citations', [])}
            references.extend(
                citations.get(rid, {'id': rid}) for rid in json.loads(message['sources'])
            )
        for reference in references:
            context.expand(db, uid, row, [reference])
        delivery = store.now()
        if body.mode == 'deadline':
            try:
                when = datetime.fromisoformat(body.deadline.replace('Z', '+00:00'))
                if when.tzinfo is None:
                    raise ValueError()
                if when <= datetime.now(timezone.utc):
                    raise ValueError()
                delivery = when.astimezone(timezone.utc).isoformat()
            except ValueError:
                raise DomainError(422, '请选择未来的送达时间，时间必须包含时区。')
        status = 'waiting' if body.mode == 'now' else 'scheduled'
        brief = _handoff_brief(db, row, body.note)
        db.execute(
            'UPDATE accord_threads SET status=?,delivery_at=?,handoff_note=?,updated_at=? WHERE id=?',
            (status, delivery, brief, store.now(), tid),
        )
        _message(
            db,
            tid,
            'system',
            uid,
            '已请本人处理。' if status == 'waiting' else '已安排在指定时间送达本人。',
        )
        return {'status': status, 'delivery_at': delivery}

    return operate(uid, body, 'handoff:' + tid, run)


def confirm(*, tid: str, body: Confirmation, uid):
    conclusion = text(body.conclusion)
    title = text(body.task_title)

    def run(db):
        row = thread_for(uid, tid, db)
        if uid != row['target_id'] or row['kind'] != 'peer':
            raise DomainError(403, '需要被找的本人确认。')
        if row['status'] not in ('waiting', 'human'):
            raise DomainError(409, '这条协作当前不能确认。')
        if body.assignee_id != uid:
            raise DomainError(422, '请由任务负责人本人确认承担。')
        task_id = store.new_id('task')
        now = store.now()
        db.execute(
            'INSERT INTO tasks(id,title,detail,status,assignee_id,assign_reason,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
            (task_id, title, conclusion, 'open', uid, '本人确认', now, now),
        )
        db.execute(
            'INSERT INTO accord_task_acl(task_id,creator_id,thread_id) VALUES(?,?,?)',
            (task_id, row['owner_id'], tid),
        )
        _message(db, tid, 'human', uid, conclusion)
        _message(
            db, tid, 'system', uid, '本人已确认，并加入待办：' + title, meta={'task_id': task_id}
        )
        db.execute(
            "UPDATE accord_threads SET status='resolved',updated_at=? WHERE id=?", (now, tid)
        )
        return {'task_id': task_id}

    return operate(uid, body, 'confirm:' + tid, run)


def task_status(*, task_id: str, body: TaskStatus, uid):
    def run(db):
        task = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
        if not task or task['assignee_id'] != uid:
            raise DomainError(404, '待办不存在或需要负责人操作。')
        db.execute(
            'UPDATE tasks SET status=?,updated_at=? WHERE id=?', (body.status, store.now(), task_id)
        )
        return {'status': body.status}

    return operate(uid, body, 'task_status:' + task_id, run)


def delete_task(*, task_id: str, body: TaskDelete, uid):
    def run(db):
        task = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
        if not task or task['assignee_id'] != uid:
            raise DomainError(404, '待办不存在或需要负责人操作。')

        now = store.now()
        db.execute(
            "UPDATE accord_flows SET status='cancelled',updated_at=? WHERE kind='task_summary' AND task_id=?",
            (now, task_id),
        )
        db.execute(
            """UPDATE accord_flow_calls SET status='cancelled'
            WHERE status='running' AND flow_id IN (
              SELECT id FROM accord_flows WHERE kind='task_summary' AND task_id=?
            )""",
            (task_id,),
        )
        db.execute(
            "UPDATE accord_flow_actions SET status='dismissed',task_id='' WHERE task_id=?",
            (task_id,),
        )
        db.execute(
            "UPDATE accord_flows SET status='cancelled',task_id='',updated_at=? WHERE kind='assignment' AND task_id=?",
            (now, task_id),
        )
        db.execute("UPDATE artifacts SET task_id='' WHERE task_id=?", (task_id,))
        db.execute('DELETE FROM accord_task_priorities WHERE task_id=?', (task_id,))
        db.execute('DELETE FROM accord_task_acl WHERE task_id=?', (task_id,))
        db.execute('DELETE FROM tasks WHERE id=?', (task_id,))
        return {'deleted': True}

    return operate(uid, body, 'task_delete:' + task_id, run)


def pair_threads(db, uid, peer):
    result = []
    for row in db.execute(
        "SELECT id FROM accord_threads WHERE kind='peer' AND ((owner_id=? AND target_id=?) OR (owner_id=? AND target_id=?)) ORDER BY created_at,rowid",
        (uid, peer, peer, uid),
    ).fetchall():
        try:
            result.append(access.thread_for(uid, row['id'], db))
        except DomainError:
            pass
    return result


def open_chat(*, body: OpenChat, uid):
    def run(db):
        if (
            uid == body.target_id
            or not identity.shares_account_roster(uid, body.target_id)
            or not db.execute(
                'SELECT 1 FROM accord_accounts WHERE unit_id=?', (body.target_id,)
            ).fetchone()
        ):
            raise DomainError(404, '请选择一位同事。')
        existing = pair_threads(db, uid, body.target_id)
        if not body.new_item and existing:
            return {'id': max(existing, key=lambda t: (t['updated_at'], t['id']))['id']}
        # Repeated clicks cannot create several empty or concurrently running requests.
        # Once a request has an answer (or has otherwise stopped), an explicit new item
        # starts a fresh segment instead of reopening the old conversation.
        own = [
            t
            for t in existing
            if t['owner_id'] == uid
            and t['status'] == 'agent'
            and t['purpose'] == 'ordinary'
            and (
                not db.execute(
                    'SELECT 1 FROM messages WHERE conversation_id=? LIMIT 1', (t['id'],)
                ).fetchone()
                or runtime.active(db, t['id'])
            )
        ]
        if own:
            return {'id': max(own, key=lambda t: (t['updated_at'], t['id']))['id']}
        tid, now = store.new_id('thread'), store.now()
        db.execute(
            'INSERT INTO accord_threads(id,owner_id,target_id,title,kind,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
            (tid, uid, body.target_id, '新的协作', 'peer', now, now),
        )
        return {'id': tid}

    return operate(uid, body, 'chat:open', run)
