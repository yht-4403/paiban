from datetime import datetime, timedelta, timezone

from accord_api.modules.activity.schemas import Availability, Heartbeat, Preference, Priority
from accord_api.modules.identity import service as identity
from accord_api.modules.permissions import policy as access
from accord_api.modules.topics import service as topics
from accord_api.platform.commands import expect, operate
from accord_api.platform.db import database as store
from accord_api.platform.errors import DomainError


def preferences(db, uid):
    row = db.execute(
        'SELECT * FROM accord_activity_preferences WHERE owner_id=?', (uid,)
    ).fetchone()
    return (
        {
            'automatic': bool(row['automatic']),
            'work_title': bool(row['work_title']),
            'version': row['version'],
        }
        if row
        else {'automatic': False, 'work_title': False, 'version': 0}
    )


def preference(*, body: Preference, uid):
    def run(db):
        current = preferences(db, uid)
        expect(current['version'], body.expected_version)
        db.execute(
            """INSERT INTO accord_activity_preferences VALUES(?,?,?,?) ON CONFLICT(owner_id)
          DO UPDATE SET automatic=excluded.automatic,work_title=excluded.work_title,version=excluded.version""",
            (
                uid,
                int(body.automatic),
                int(body.automatic and body.work_title),
                current['version'] + 1,
            ),
        )
        if not body.automatic:
            db.execute('DELETE FROM accord_presence WHERE owner_id=?', (uid,))
        return preferences(db, uid)

    return operate(uid, body, 'activity:preference', run)


def heartbeat(*, body: Heartbeat, uid):
    with store.lock, store.connection():
        db = store.connection()
        if not preferences(db, uid)['automatic']:
            return {'recorded': False}
        if body.thread_id:
            access.thread_for(uid, body.thread_id, db)
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        db.execute('DELETE FROM accord_presence WHERE owner_id=? AND seen_at<?', (uid, cutoff))
        if (
            not db.execute(
                'SELECT 1 FROM accord_presence WHERE owner_id=? AND client_id=?',
                (uid, body.client_id),
            ).fetchone()
            and db.execute(
                'SELECT count(*) FROM accord_presence WHERE owner_id=?', (uid,)
            ).fetchone()[0]
            >= 16
        ):
            raise DomainError(429, '当前活跃页面过多，请关闭不用的页面。')
        db.execute(
            """INSERT INTO accord_presence VALUES(?,?,?,?,?,?) ON CONFLICT(owner_id,client_id)
          DO UPDATE SET surface=excluded.surface,thread_id=excluded.thread_id,active=excluded.active,seen_at=excluded.seen_at""",
            (uid, body.client_id, body.surface, body.thread_id, int(body.active), store.now()),
        )
        return {'recorded': True}


def task_priority(db, task_id):
    row = db.execute(
        'SELECT priority FROM accord_task_priorities WHERE task_id=?', (task_id,)
    ).fetchone()
    return row['priority'] if row else 'normal'


def priority(*, tid: str, body: Priority, uid):
    def run(db):
        if not db.execute(
            'SELECT 1 FROM tasks WHERE id=? AND assignee_id=?', (tid, uid)
        ).fetchone():
            raise DomainError(404, '待办不存在或需要负责人操作。')
        db.execute(
            """INSERT INTO accord_task_priorities VALUES(?,?) ON CONFLICT(task_id) DO UPDATE SET priority=excluded.priority""",
            (tid, body.priority),
        )
        return {'priority': body.priority}

    return operate(uid, body, 'task:priority:' + tid, run)


def visible(db, viewer, subject):
    if not identity.shares_account_roster(viewer, subject):
        raise DomainError(404, '成员不存在。')
    unit = db.execute(
        'SELECT u.* FROM units u JOIN accord_accounts a ON a.unit_id=u.id WHERE u.id=?', (subject,)
    ).fetchone()
    if not unit:
        raise DomainError(404, '成员不存在。')
    pref = preferences(db, subject)
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=75)).isoformat()
    presence = (
        db.execute(
            'SELECT * FROM accord_presence WHERE owner_id=? AND active=1 AND seen_at>? ORDER BY seen_at DESC LIMIT 1',
            (subject, cutoff),
        ).fetchone()
        if pref['automatic']
        else None
    )
    label = '专注中' if unit['window'] == 'closed' else '可协作'
    result = {
        'label': label,
        'availability': label,
        'source': '本人设置',
        'seen_at': None,
        'agent_working': False,
        'work': None,
        'meeting': '未接入会议状态',
        'shared_tasks': [],
        'permission_version': pref['version'],
    }
    if pref['automatic']:
        result.update(
            label=('在拍办聊天' if presence['surface'] == 'chat' else '在拍办工作')
            if presence and unit['window'] != 'closed'
            else label,
            source='拍办' if presence else '本人设置',
            seen_at=presence['seen_at'] if presence else None,
            agent_working=bool(
                db.execute(
                    "SELECT 1 FROM accord_runs WHERE actor_id=? AND status IN ('queued','running')",
                    (subject,),
                ).fetchone()
            ),
        )
    if presence and presence['thread_id'] and pref['work_title']:
        try:
            current = access.thread_for(subject, presence['thread_id'], db)
            allowed = (
                current['kind'] == 'workspace'
                and current['purpose'] == 'ordinary'
                and current['owner_id'] == subject
            )
            if not allowed:
                access.thread_for(viewer, current['id'], db)
                allowed = True
            if allowed:
                result['work'] = {
                    'title': current['title'],
                    'kind': 'chat' if current['kind'] == 'peer' else 'work',
                }
        except DomainError:
            pass
    for row in db.execute(
        """SELECT t.*,a.thread_id,a.creator_id FROM tasks t JOIN accord_task_acl a ON a.task_id=t.id
        WHERE t.assignee_id=? AND (t.assignee_id=? OR a.creator_id=?) ORDER BY t.created_at DESC""",
        (subject, viewer, viewer),
    ):
        if not identity.shares_account_roster(row['creator_id'], subject):
            continue
        try:
            access.thread_for(viewer, row['thread_id'], db)
        except DomainError:
            continue
        result['shared_tasks'].append(
            topics.task_projection(
                db,
                viewer,
                {
                    'id': row['id'],
                    'title': row['title'],
                    'status': row['status'],
                    'assignee_id': row['assignee_id'],
                    'creator_id': row['creator_id'],
                    'priority': task_priority(db, row['id']),
                    'thread_id': row['thread_id'],
                },
            )
        )
    result['progress'] = {
        'completed': sum(task['status'] == 'done' for task in result['shared_tasks']),
        'total': len(result['shared_tasks']),
        'scope': '你有权查看的待办',
    }
    return result


def member_activity(*, uid: str, viewer):
    with store.lock:
        return visible(store.connection(), viewer, uid)


def availability(*, body: Availability, uid):
    def run(db):
        db.execute('UPDATE units SET window=? WHERE id=?', (body.window, uid))
        return {'window': body.window}

    return operate(uid, body, 'availability', run)
