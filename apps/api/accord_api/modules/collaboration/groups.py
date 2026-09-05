from accord_api.modules.agent_runs import service as runtime
from accord_api.modules.collaboration.groups_schemas import (
    AddMembers,
    CreateGroup,
    GroupMessage,
    RenameGroup,
)
from accord_api.modules.collaboration.repository import message, row_msg
from accord_api.modules.identity import service as identity
from accord_api.modules.permissions import policy as access
from accord_api.platform.commands import operate, text
from accord_api.platform.db import database as store
from accord_api.platform.errors import DomainError


def group_for(db, uid, tid):
    group = access.thread_for(uid, tid, db)
    if group['kind'] != 'group':
        raise DomainError(404, '群聊不存在。')
    return group


def check_members(db, actor, ids):
    for member in ids:
        if (
            not identity.shares_account_roster(actor, member)
            or not db.execute('SELECT 1 FROM accord_accounts WHERE unit_id=?', (member,)).fetchone()
        ):
            raise DomainError(404, '成员不存在。')


def list_groups(db, uid):
    result = []
    for row in db.execute(
        'SELECT thread_id FROM accord_group_members WHERE member_id=?', (uid,)
    ).fetchall():
        group = group_for(db, uid, row['thread_id'])
        last = db.execute(
            "SELECT * FROM messages WHERE conversation_id=? AND rowid>=? AND body!='' ORDER BY rowid DESC LIMIT 1",
            (group['id'], access.message_floor(db, group, uid)),
        ).fetchone()
        result.append({**group, 'preview': row_msg(last, uid, db)['body'][:70] if last else ''})
    return sorted(result, key=lambda g: (g['updated_at'], g['id']), reverse=True)


def create_group(*, body: CreateGroup, uid):
    def run(db):
        others = list(dict.fromkeys(member for member in body.member_ids if member != uid))
        if len(others) < 2:
            raise DomainError(422, '请至少选择两位同事。')
        check_members(db, uid, others)
        if (
            db.execute(
                "SELECT count(*) FROM accord_threads WHERE kind='group' AND owner_id=?", (uid,)
            ).fetchone()[0]
            >= 50
        ):
            raise DomainError(422, '创建的群聊已达到上限。')
        members = [uid, *others]
        names = [
            db.execute('SELECT person_name FROM units WHERE id=?', (member,)).fetchone()[
                'person_name'
            ]
            for member in members
        ]
        title = text(body.title) if body.title.strip() else '、'.join(names)[:80]
        tid, now = store.new_id('group'), store.now()
        db.execute(
            'INSERT INTO accord_threads(id,owner_id,target_id,title,kind,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
            (tid, uid, uid, title, 'group', now, now),
        )
        db.executemany(
            'INSERT INTO accord_group_members(thread_id,member_id) VALUES(?,?)',
            [(tid, member) for member in members],
        )
        message(db, tid, 'system', uid, '群聊已创建')
        return {'id': tid}

    return operate(uid, body, 'group:create', run)


def add_members(*, tid: str, body: AddMembers, uid):
    def run(db):
        group = group_for(db, uid, tid)
        if group['owner_id'] != uid:
            raise DomainError(403, '由群主邀请成员。')
        if runtime.active(db, tid):
            raise DomainError(409, '请等待当前回答完成，再邀请成员。')
        if db.execute('SELECT 1 FROM accord_flows WHERE thread_id=?', (tid,)).fetchone():
            raise DomainError(409, '本轮会议参会范围已确定，请另开会议邀请其他成员。')
        new = sorted(set(body.member_ids) - set(group['member_ids']))
        check_members(db, uid, new)
        if len(new) + len(group['member_ids']) > 8:
            raise DomainError(422, '每个群最多 8 位成员。')
        if new:
            floor = db.execute('SELECT coalesce(max(rowid),0)+1 FROM messages').fetchone()[0]
            db.executemany(
                'INSERT INTO accord_group_members VALUES(?,?,?)',
                [(tid, member, floor) for member in new],
            )
            names = [
                db.execute('SELECT person_name FROM units WHERE id=?', (member,)).fetchone()[
                    'person_name'
                ]
                for member in new
            ]
            message(
                db, tid, 'system', uid, '、'.join(names) + '加入群聊；新成员从此处开始查看消息。'
            )
            db.execute('UPDATE accord_threads SET updated_at=? WHERE id=?', (store.now(), tid))
        return {'member_ids': sorted(set(group['member_ids']) | set(new))}

    return operate(uid, body, 'group:members:' + tid, run)


def rename_group(*, tid: str, body: RenameGroup, uid):
    def run(db):
        group = group_for(db, uid, tid)
        if group['owner_id'] != uid:
            raise DomainError(403, '由群主修改群名。')
        db.execute(
            'UPDATE accord_threads SET title=?,updated_at=? WHERE id=?',
            (text(body.title), store.now(), tid),
        )
        return {'title': text(body.title)}

    return operate(uid, body, 'group:rename:' + tid, run)


def send_message(*, tid: str, body: GroupMessage, uid):
    def run(db):
        group = group_for(db, uid, tid)
        if group['status'] == 'closed':
            raise DomainError(409, '会议已经结束。')
        if body.agent_id and body.agent_id not in group['member_ids']:
            raise DomainError(404, '请选择群成员的 Agent。')
        if body.agent_id and runtime.active(db, tid):
            raise DomainError(409, '请等待当前回答完成。')
        for rid in body.source_ids:
            resource = access.resource_for(db, uid, rid)
            if not access.compatible(db, group, resource):
                raise DomainError(403, '资料须对所有群成员可见。')
        mid = message(
            db,
            tid,
            'human',
            uid,
            text(body.body),
            body.source_ids,
            meta={'agent_id': body.agent_id},
        )
        rid = None
        if body.agent_id:
            assistant = message(db, tid, 'agent', body.agent_id, '')
            rid = runtime.enqueue(db, tid, uid, mid, assistant, body.source_ids)
        db.execute('UPDATE accord_threads SET updated_at=? WHERE id=?', (store.now(), tid))
        return {'id': mid, 'run_id': rid}

    return operate(uid, body, 'group:message:' + tid, run)
