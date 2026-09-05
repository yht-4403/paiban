import json
from datetime import datetime, timedelta, timezone

from accord_api.modules.collaboration import repository
from accord_api.modules.coordination import source_scope
from accord_api.modules.identity import service as identity
from accord_api.modules.knowledge import person_context
from accord_api.modules.permissions import policy as access
from accord_api.platform.commands import operate, text
from accord_api.platform.db import database as store
from accord_api.platform.errors import DomainError


def can_view(db, uid, row):
    if not identity.shares_account_roster(uid, row['owner_id']):
        return False
    if uid == row['owner_id']:
        return True
    if row['kind'] == 'chat_summary':
        return uid in json.loads(row['member_ids'])
    if row['kind'] == 'assignment':
        return bool(
            row['task_id']
            and db.execute(
                'SELECT 1 FROM tasks WHERE id=? AND assignee_id=?', (row['task_id'], uid)
            ).fetchone()
        )
    return bool(
        row['thread_id']
        and db.execute(
            'SELECT 1 FROM accord_group_members WHERE thread_id=? AND member_id=?',
            (row['thread_id'], uid),
        ).fetchone()
    )


def flow_for(db, uid, fid):
    row = db.execute('SELECT * FROM accord_flows WHERE id=?', (fid,)).fetchone()
    if not row or not can_view(db, uid, row):
        raise DomainError(404, '事项不存在或不可见。')
    return dict(row)


def insert(db, uid, kind, title, body, members, thread_id='', source_ids=None):
    if any(not identity.shares_account_roster(uid, member) for member in members):
        raise DomainError(422, '请选择当前账号组的成员。')
    fid = store.new_id('flow')
    now = store.now()
    source_ids = list(source_ids or [])
    db.execute(
        'INSERT INTO accord_flows(id,owner_id,kind,title,body,member_ids,source_ids,thread_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
        (
            fid,
            uid,
            kind,
            title,
            body,
            json.dumps(members),
            json.dumps(source_ids),
            thread_id,
            now,
            now,
        ),
    )
    return {'id': fid}


def start(body, uid):
    def run(db):
        members = list(dict.fromkeys([uid, *body.member_ids]))
        if len(members) > 8 or any(
            not identity.shares_account_roster(uid, m)
            or not db.execute('SELECT 1 FROM accord_accounts WHERE unit_id=?', (m,)).fetchone()
            for m in members
        ):
            raise DomainError(422, '请选择当前工作空间的成员，最多 8 人。')
        if db.execute(
            "SELECT 1 FROM accord_flows WHERE owner_id=? AND status IN ('queued','running','summarizing')",
            (uid,),
        ).fetchone():
            raise DomainError(409, '上一项仍在整理，请完成后再发起。')
        source_ids = source_scope.validate(db, members, body.source_ids)
        return insert(
            db,
            uid,
            body.kind,
            text(body.title),
            text(body.body),
            members,
            source_ids=source_ids,
        )

    return operate(uid, body, 'flow:start', run)


def list_flows(db, uid):
    result = []
    for row in db.execute(
        'SELECT id,owner_id,kind,title,status,thread_id,task_id,member_ids,created_at,updated_at FROM accord_flows ORDER BY updated_at DESC'
    ):
        if can_view(db, uid, row):
            next_meeting = follow_up(db, row['id'])
            result.append(
                {
                    **dict(row),
                    'member_ids': json.loads(row['member_ids']),
                    'pending_action_count': db.execute(
                        "SELECT count(*) FROM accord_flow_actions WHERE flow_id=? AND assignee_id=? AND status='suggested'",
                        (row['id'], uid),
                    ).fetchone()[0],
                    'follow_up_ready': next_meeting['ready']
                    and next_meeting['status'] == 'suggested',
                }
            )
    return result


def detail(uid, fid):
    with store.lock:
        db = store.connection()
        f = flow_for(db, uid, fid)
        public = {key: value for key, value in f.items() if key != 'source_ids'}
        evidence = json.loads(f['evidence'])
        try:
            for e in evidence:
                person_context.validate(db, e['sources'], json.loads(f['member_ids']), strict=False)
        except DomainError:
            return {
                **public,
                'result': {},
                'evidence': [],
                'actions': [],
                'member_ids': json.loads(f['member_ids']),
                'error': '来源共享范围已改变，请由发起人重新收集。',
                'sources_changed': True,
            }
        return {
            **public,
            'member_ids': json.loads(f['member_ids']),
            'result': json.loads(f['result']),
            'evidence': [
                {
                    'person_id': e['person_id'],
                    'answer': e['answer'],
                    'sources': [
                        {k: r[k] for k in ('id', 'title', 'source_kind', 'version', 'updated_at')}
                        for r in e['sources']
                    ],
                }
                for e in evidence
            ],
            'actions': [
                dict(r)
                for r in db.execute(
                    'SELECT a.*,t.status AS task_status,t.artifact AS task_artifact FROM accord_flow_actions a LEFT JOIN tasks t ON t.id=a.task_id WHERE a.flow_id=?',
                    (fid,),
                )
            ],
            'follow_up': follow_up(db, fid),
        }


def follow_up(db, fid):
    saved = db.execute(
        'SELECT status,next_flow_id FROM accord_flow_followups WHERE flow_id=?', (fid,)
    ).fetchone()
    rows = db.execute(
        """SELECT a.status,t.status AS task_status FROM accord_flow_actions a
        LEFT JOIN tasks t ON t.id=a.task_id WHERE a.flow_id=?""",
        (fid,),
    ).fetchall()
    accepted = [row for row in rows if row['status'] == 'accepted']
    ready = bool(
        accepted
        and not any(row['status'] == 'suggested' for row in rows)
        and all(row['task_status'] == 'done' for row in accepted)
    )
    return {
        'ready': ready,
        'status': saved['status'] if saved else ('suggested' if ready else 'waiting'),
        'next_flow_id': saved['next_flow_id'] if saved else '',
        'completed_count': sum(row['task_status'] == 'done' for row in accepted),
        'task_count': len(accepted),
    }


def set_sharing(body, uid):
    def run(db):
        if body.source_kind == 'state':
            if body.source_id != uid:
                raise DomainError(403, '只能设置自己的共享范围。')
        else:
            t = access.thread_for(uid, body.source_id, db)
            if t['owner_id'] != uid or t['kind'] != 'workspace' or t['purpose'] != 'ordinary':
                raise DomainError(403, '只可共享本人的普通工作会话。')
        db.execute(
            'INSERT INTO accord_context_grants VALUES(?,?,?,?,1) ON CONFLICT(owner_id,source_kind,source_id) DO UPDATE SET enabled=excluded.enabled,version=version+1',
            (uid, body.source_kind, body.source_id, int(body.enabled)),
        )
        return person_context.grant(db, uid, body.source_kind, body.source_id)

    return operate(uid, body, 'context:share', run)


def sharing(uid):
    return [
        dict(r)
        for r in store.query(
            'SELECT source_kind,source_id,enabled,version FROM accord_context_grants WHERE owner_id=?',
            (uid,),
        )
    ]


def group(db, uid, title, members):
    tid = store.new_id('thread')
    now = store.now()
    db.execute(
        'INSERT INTO accord_threads(id,owner_id,target_id,title,kind,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
        (tid, uid, uid, title, 'group', now, now),
    )
    for member in members:
        db.execute('INSERT INTO accord_group_members VALUES(?,?,0)', (tid, member))
    repository.message(db, tid, 'system', uid, '会议已开始。')
    return tid


def create_task(db, creator, assignee, title, detail, thread_id='', reason='任务分配'):
    if not identity.shares_account_roster(creator, assignee):
        raise DomainError(422, '请选择当前账号组的成员。')
    if (
        not thread_id
        or not db.execute('SELECT 1 FROM accord_threads WHERE id=?', (thread_id,)).fetchone()
    ):
        thread_id = store.new_id('thread')
        now = store.now()
        db.execute(
            "INSERT INTO accord_threads(id,owner_id,target_id,title,kind,status,created_at,updated_at) VALUES(?,?,?,?,?,'closed',?,?)",
            (
                thread_id,
                creator,
                assignee,
                title,
                'peer' if creator != assignee else 'workspace',
                now,
                now,
            ),
        )
    task_id = store.new_id('task')
    now = store.now()
    db.execute(
        'INSERT INTO tasks(id,title,detail,status,assignee_id,assign_reason,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
        (task_id, title, detail, 'open', assignee, reason, now, now),
    )
    db.execute('INSERT INTO accord_task_acl VALUES(?,?,?)', (task_id, creator, thread_id))
    repository.message(
        db,
        thread_id,
        'system',
        creator,
        ('已分配待办：' if reason == '任务分配' else '已加入待办：') + title,
        meta={'task_id': task_id},
    )
    return task_id, thread_id


def choose(body, uid, fid):
    def run(db):
        f = flow_for(db, uid, fid)
        if uid != f['owner_id']:
            raise DomainError(403, '由发起人选择。')
        if f['status'] != 'ready':
            raise DomainError(409, '当前不能重复选择，请刷新。')
        evidence = json.loads(f['evidence'])
        audience = json.loads(f['member_ids'])
        for e in evidence:
            person_context.validate(db, e['sources'], audience)
        members = list(dict.fromkeys(body.member_ids))
        if not set(members) <= set(audience):
            raise DomainError(422, '请选择本轮成员。')
        if f['kind'] == 'assignment':
            candidates = {c['person_id'] for c in json.loads(f['result']).get('candidates', [])}
            if len(members) != 1 or members[0] not in candidates:
                raise DomainError(422, '请选择一位推荐人选。')
            task_id, tid = create_task(db, uid, members[0], f['title'], f['body'])
            db.execute(
                "UPDATE accord_flows SET status='assigned',task_id=?,thread_id=?,updated_at=? WHERE id=?",
                (task_id, tid, store.now(), fid),
            )
            return {'task_id': task_id, 'thread_id': tid}
        if f['kind'] != 'decision':
            raise DomainError(422, '同步简报无需开会。')
        members = list(dict.fromkeys([uid, *members]))
        if len(members) < 2:
            raise DomainError(422, '请至少选择一位同事。')
        tid = group(db, uid, f['title'], members)
        # The original evidence audience remains fixed and deliberately conservative.
        db.execute(
            "UPDATE accord_flows SET status='live',thread_id=?,updated_at=? WHERE id=?",
            (tid, store.now(), fid),
        )
        repository.message(db, tid, 'system', uid, json.loads(f['result'])['summary'])
        return {'thread_id': tid}

    return operate(uid, body, 'flow:choose:' + fid, run)


def close_thread(db, uid, tid):
    t = access.thread_for(uid, tid, db)
    old = db.execute(
        "SELECT id FROM accord_flows WHERE kind='chat_summary' AND thread_id=?", (tid,)
    ).fetchone()
    if old:
        return {'id': old['id']}
    if t['kind'] != 'peer' or t['status'] not in ('waiting', 'human', 'resolved'):
        raise DomainError(409, '请在本人通道中结束本轮聊天。')
    if db.execute(
        "SELECT 1 FROM accord_runs WHERE thread_id=? AND status IN ('queued','running')", (tid,)
    ).fetchone():
        raise DomainError(409, '请先等待回答结束。')
    result = insert(db, uid, 'chat_summary', t['title'], '', access.participants(t), tid)
    db.execute(
        "UPDATE accord_threads SET status='closed',updated_at=? WHERE id=?", (store.now(), tid)
    )
    repository.message(db, tid, 'system', uid, '本轮聊天已结束，正在整理。')
    return result


def close_chat(body, uid, tid):
    return operate(uid, body, 'chat:close:' + tid, lambda db: close_thread(db, uid, tid))


def finish_meeting(body, uid, fid):
    def run(db):
        f = flow_for(db, uid, fid)
        if uid != f['owner_id']:
            raise DomainError(403, '由发起人结束会议。')
        if f['status'] in ('summarizing', 'closed'):
            return {'id': fid}
        if f['status'] != 'live':
            raise DomainError(409, '会议尚未开始。')
        if db.execute(
            "SELECT 1 FROM accord_runs WHERE thread_id=? AND status IN ('queued','running')",
            (f['thread_id'],),
        ).fetchone():
            raise DomainError(409, '请等待当前回答结束。')
        db.execute("UPDATE accord_threads SET status='closed' WHERE id=?", (f['thread_id'],))
        db.execute(
            "UPDATE accord_flows SET status='summarizing',updated_at=? WHERE id=?",
            (store.now(), fid),
        )
        return {'id': fid}

    return operate(uid, body, 'flow:finish:' + fid, run)


def action(body, uid, action_id, accept):
    def run(db):
        row = db.execute(
            'SELECT * FROM accord_flow_actions WHERE id=?', (action_id,)
        ).fetchone()
        if not row:
            raise DomainError(404, '建议不存在。')
        f = flow_for(db, uid, row['flow_id'])
        if uid not in (row['assignee_id'], f['owner_id']):
            raise DomainError(404, '建议不存在或需要负责人操作。')
        if row['status'] != 'suggested':
            return {'task_id': row['task_id']}
        task_id = ''
        if accept:
            task_id, _ = create_task(
                db,
                f['owner_id'],
                row['assignee_id'],
                row['title'],
                row['detail'],
                f['thread_id'],
                reason='会议分配' if uid == f['owner_id'] else '本人加入',
            )
        db.execute(
            'UPDATE accord_flow_actions SET status=?,task_id=? WHERE id=?',
            ('accepted' if accept else 'dismissed', task_id, action_id),
        )
        return {'task_id': task_id}

    return operate(uid, body, 'flow:action:' + action_id + str(accept), run)


def continue_flow(body, uid, fid):
    def run(db):
        f = flow_for(db, uid, fid)
        if uid != f['owner_id']:
            raise DomainError(403, '由会议发起人决定是否继续。')
        status = follow_up(db, fid)
        if status['status'] == 'created':
            return {'id': status['next_flow_id']}
        if not status['ready']:
            raise DomainError(409, '关联待办尚未全部完成。')
        if body.action == 'dismiss':
            db.execute(
                """INSERT INTO accord_flow_followups(flow_id,status,next_flow_id,updated_at)
                VALUES(?,'dismissed','',?) ON CONFLICT(flow_id) DO UPDATE SET
                status='dismissed',next_flow_id='',updated_at=excluded.updated_at""",
                (fid, store.now()),
            )
            return {'id': ''}
        result = json.loads(f['result'])
        title = text('跟进：' + f['title'])[:160]
        next_result = insert(
            db,
            uid,
            body.kind,
            title,
            '上一轮会议的关联待办已经全部完成。请结合成员最新共享资料与待办完成结果，汇总新增事实、仍未解决的问题，并判断下一步。\n\n上一轮纪要：'
            + result.get('summary', '')[:4000],
            json.loads(f['member_ids']),
        )
        db.execute(
            """INSERT INTO accord_flow_followups(flow_id,status,next_flow_id,updated_at)
            VALUES(?,'created',?,?) ON CONFLICT(flow_id) DO UPDATE SET
            status='created',next_flow_id=excluded.next_flow_id,updated_at=excluded.updated_at""",
            (fid, next_result['id'], store.now()),
        )
        return next_result

    return operate(uid, body, 'flow:follow-up:' + fid + ':' + body.action, run)


def retry(body, uid, fid):
    def run(db):
        f = flow_for(db, uid, fid)
        if uid != f['owner_id'] or f['status'] not in ('error', 'ready'):
            raise DomainError(409, '当前不能重新整理。')
        status = 'summarizing' if f['thread_id'] and f['kind'] == 'decision' else 'queued'
        db.execute(
            'UPDATE accord_flows SET status=?,error=?,result=?,evidence=?,updated_at=? WHERE id=?',
            (status, '', '{}', '[]', store.now(), fid),
        )
        return {'id': fid}

    return operate(uid, body, 'flow:retry:' + fid, run)


def close_idle():
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    with store.lock, store.connection() as db:
        rows = db.execute(
            "SELECT id,owner_id FROM accord_threads WHERE kind='peer' AND status IN ('human','resolved') AND updated_at<?",
            (cutoff,),
        ).fetchall()
        for row in rows:
            try:
                close_thread(db, row['owner_id'], row['id'])
            except DomainError:
                pass
