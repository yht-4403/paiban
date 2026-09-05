"""Audience checks shared by old routes, new workspaces, and the model runtime."""

from accord_api.modules.identity import service as identity
from accord_api.platform.db import database as store
from accord_api.platform.errors import DomainError


def round_for(db, uid, round_id):
    row = db.execute(
        """SELECT r.* FROM accord_rounds r JOIN accord_round_members m ON m.round_id=r.id
        WHERE r.id=? AND m.member_id=?""",
        (round_id, uid),
    ).fetchone()
    if not row or not identity.shares_account_roster(uid, row['owner_id']):
        raise DomainError(404, '课题不存在或你没有查看权限。')
    return dict(row)


def scope_for(db, tid):
    row = db.execute('SELECT * FROM accord_thread_scopes WHERE thread_id=?', (tid,)).fetchone()
    return dict(row) if row else {'thread_id': tid, 'purpose': 'ordinary', 'round_id': ''}


def thread_for(uid, tid, db=None):
    if db is None:
        with store.lock:
            return thread_for(uid, tid, store.connection())
    row = db.execute('SELECT * FROM accord_threads WHERE id=?', (tid,)).fetchone()
    if not row:
        raise DomainError(404, '协作不存在或你没有查看权限。')
    if not identity.shares_account_roster(uid, row['owner_id']):
        raise DomainError(404, '协作不存在或你没有查看权限。')
    scope = scope_for(db, tid)
    private = scope['purpose'] in ('exploration', 'review')
    allowed = row['owner_id'] == uid or (
        not private
        and row['target_id'] == uid
        and row['status'] in ('waiting', 'human', 'resolved', 'closed')
    )
    member_ids = (
        [
            r['member_id']
            for r in db.execute(
                'SELECT member_id FROM accord_group_members WHERE thread_id=? ORDER BY member_id',
                (tid,),
            )
        ]
        if row['kind'] == 'group'
        else []
    )
    if row['kind'] == 'group':
        allowed = uid in member_ids and all(
            identity.shares_account_roster(row['owner_id'], member) for member in member_ids
        )
    elif not identity.shares_account_roster(row['owner_id'], row['target_id']):
        allowed = False
    if not allowed:
        raise DomainError(404, '协作不存在或你没有查看权限。')
    if scope['round_id']:
        round_for(db, uid, scope['round_id'])
    placement = db.execute(
        'SELECT folder_id,version FROM accord_placements WHERE owner_id=? AND thread_id=?',
        (uid, tid),
    ).fetchone()
    return {
        **dict(row),
        'member_ids': member_ids,
        'purpose': scope['purpose'],
        'round_id': scope['round_id'],
        'folder_id': placement['folder_id'] if placement else '',
        'placement_version': placement['version'] if placement else 0,
    }


def participants(thread):
    if thread['kind'] == 'group':
        return thread['member_ids']
    # A person's Agent route is an audience boundary even before handing the chat to them.
    return (
        list(dict.fromkeys([thread['owner_id'], thread['target_id']]))
        if thread['kind'] == 'peer'
        else [thread['owner_id']]
    )


def can_read(db, uid, resource):
    if (
        not resource
        or not resource['active']
        or not db.execute('SELECT 1 FROM accord_accounts WHERE unit_id=?', (uid,)).fetchone()
        or not db.execute(
            'SELECT 1 FROM accord_accounts WHERE unit_id=?', (resource['owner_id'],)
        ).fetchone()
        or not identity.shares_account_roster(uid, resource['owner_id'])
    ):
        return False
    if resource['scope'] == 'team':
        return True
    if resource['scope'] == 'private':
        return resource['owner_id'] == uid
    return bool(
        resource['scope'] == 'round'
        and db.execute(
            'SELECT 1 FROM accord_round_members WHERE round_id=? AND member_id=?',
            (resource['round_id'], uid),
        ).fetchone()
    )


def resource_for(db, uid, resource_id, version=None):
    row = db.execute('SELECT * FROM accord_resources WHERE id=?', (resource_id,)).fetchone()
    if not can_read(db, uid, row):
        raise DomainError(404, '资料不存在或当前无权读取。')
    content = db.execute(
        'SELECT * FROM accord_resource_versions WHERE resource_id=? AND version=?',
        (resource_id, version or row['version']),
    ).fetchone()
    if not content:
        raise DomainError(404, '资料版本不存在。')
    return {**dict(row), **dict(content), 'id': resource_id, 'unit_id': row['owner_id']}


def compatible(db, thread, resource):
    if not all(can_read(db, uid, resource) for uid in participants(thread)):
        return False
    if thread['purpose'] == 'review':
        return resource['scope'] == 'team' or (
            resource['scope'] == 'round' and resource['round_id'] == thread['round_id']
        )
    return True


def message_floor(db, thread, uid=None):
    if thread['kind'] != 'group':
        return 0
    if uid:
        row = db.execute(
            'SELECT joined_after FROM accord_group_members WHERE thread_id=? AND member_id=?',
            (thread['id'], uid),
        ).fetchone()
        if not row:
            raise DomainError(404, '群聊不存在。')
        return row['joined_after']
    return db.execute(
        'SELECT coalesce(max(joined_after),0) FROM accord_group_members WHERE thread_id=?',
        (thread['id'],),
    ).fetchone()[0]
