from accord_api.modules import knowledge as context
from accord_api.modules.collaboration import handoffs as handoffs
from accord_api.modules.permissions import policy as access
from accord_api.modules.workspace.schemas import (
    Archive,
    Bindings,
    Move,
    NewFolder,
    RenameFolder,
    Share,
)
from accord_api.platform.commands import VersionedOperation, expect, operate, text
from accord_api.platform.db import database as store
from accord_api.platform.errors import DomainError


def folder_for(db, uid, fid):
    row = db.execute(
        'SELECT * FROM accord_folders WHERE id=? AND owner_id=?', (fid, uid)
    ).fetchone()
    if not row:
        raise DomainError(404, '文件夹不存在。')
    return dict(row)


def folders(db, uid):
    return [
        {**dict(row), 'binding': context.binding(db, uid, 'folder', row['id'])}
        for row in db.execute(
            'SELECT * FROM accord_folders WHERE owner_id=? ORDER BY created_at,id', (uid,)
        )
    ]


def new_folder(*, body: NewFolder, uid):
    def run(db):
        if (
            db.execute('SELECT count(*) FROM accord_folders WHERE owner_id=?', (uid,)).fetchone()[0]
            >= 100
        ):
            raise DomainError(422, '文件夹已达到上限，请先整理现有目录。')
        fid = store.new_id('folder')
        db.execute(
            'INSERT INTO accord_folders(id,owner_id,name,created_at) VALUES(?,?,?,?)',
            (fid, uid, text(body.name), store.now()),
        )
        return {'id': fid, 'version': 1}

    return operate(uid, body, 'folder:create', run)


def rename_folder(*, fid: str, body: RenameFolder, uid):
    def run(db):
        folder = folder_for(db, uid, fid)
        expect(folder['version'], body.expected_version)
        db.execute(
            'UPDATE accord_folders SET name=?,version=version+1 WHERE id=?', (text(body.name), fid)
        )
        return {'version': folder['version'] + 1}

    return operate(uid, body, 'folder:rename:' + fid, run)


def remove_folder(*, fid: str, body: VersionedOperation, uid):
    def run(db):
        folder = folder_for(db, uid, fid)
        expect(folder['version'], body.expected_version)
        if db.execute(
            'SELECT 1 FROM accord_placements WHERE owner_id=? AND folder_id=?', (uid, fid)
        ).fetchone():
            raise DomainError(409, '请先移出文件夹内的聊天。')
        if db.execute(
            'SELECT 1 FROM accord_context_folders WHERE owner_id=? AND folder_id=?', (uid, fid)
        ).fetchone():
            raise DomainError(409, '请先从会话资料区移除这个文件夹。')
        db.execute(
            'DELETE FROM accord_bindings WHERE owner_id=? AND target_kind=? AND target_id=?',
            (uid, 'folder', fid),
        )
        db.execute('DELETE FROM accord_folders WHERE id=?', (fid,))
        return {'removed': True}

    return operate(uid, body, 'folder:remove:' + fid, run)


def move_thread(*, tid: str, body: Move, uid):
    def run(db):
        thread = access.thread_for(uid, tid, db)
        expect(thread['placement_version'], body.expected_version)
        if body.folder_id:
            folder_for(db, uid, body.folder_id)
        version = thread['placement_version'] + 1
        db.execute(
            """INSERT INTO accord_placements VALUES(?,?,?,?) ON CONFLICT(owner_id,thread_id)
            DO UPDATE SET folder_id=excluded.folder_id,version=excluded.version""",
            (uid, tid, body.folder_id, version),
        )
        return {'folder_id': body.folder_id, 'version': version}

    return operate(uid, body, 'thread:move:' + tid, run)


def update_bindings(db, uid, kind, target, body):
    if kind == 'folder':
        folder_for(db, uid, target)
        thread = None
    else:
        thread = access.thread_for(uid, target, db)
        if thread['owner_id'] != uid or thread['status'] != 'agent':
            raise DomainError(403, '当前会话不能调整 AI 资料。')
    current = context.binding(db, uid, kind, target)
    expect(current['version'], body.expected_version)
    if body.folder_ids:
        if kind != 'thread':
            raise DomainError(422, '请将文件夹加入会话资料区。')
        for fid in set(body.folder_ids):
            folder_for(db, uid, fid)
    for rid in set(body.included + body.excluded):
        resource = access.resource_for(db, uid, rid)
        if thread and not access.compatible(db, thread, resource):
            raise DomainError(403, '这份资料不适用于当前协作范围。')
    context.put_binding(
        db, uid, kind, target, body.included, body.excluded, current['version'] + 1, body.folder_ids
    )
    return {'version': current['version'] + 1}


def folder_bindings(*, fid: str, body: Bindings, uid):
    return operate(
        uid,
        body,
        'folder:bindings:' + fid,
        lambda db: update_bindings(db, uid, 'folder', fid, body),
    )


def thread_bindings(*, tid: str, body: Bindings, uid):
    return operate(
        uid,
        body,
        'thread:bindings:' + tid,
        lambda db: update_bindings(db, uid, 'thread', tid, body),
    )


def thread_context(*, tid: str, uid):
    with store.lock:
        thread = access.thread_for(uid, tid, store.connection())
        return {
            **context.effective(store.connection(), uid, thread),
            'available': context.available(store.connection(), uid, thread, False),
        }


def share(*, tid: str, body: Share, uid):
    def run(db):
        thread = access.thread_for(uid, tid, db)
        if (
            thread['owner_id'] != uid
            or thread['purpose'] != 'ordinary'
            or thread['kind'] != 'workspace'
        ):
            raise DomainError(403, '这段会话请使用所属流程的提交或交接操作。')
        refs = [{'id': rid} for rid in body.source_ids]
        return {
            'id': handoffs.create(db, uid, body.target_id, text(body.title), text(body.body), refs)
        }

    return operate(uid, body, 'thread:share:' + tid, run)


def archive_thread(*, tid: str, body: Archive, uid):
    def run(db):
        thread = access.thread_for(uid, tid, db)
        if (
            thread['owner_id'] != uid
            or thread['kind'] != 'workspace'
            or thread['purpose'] != 'ordinary'
        ):
            raise DomainError(403, '只能移除自己的个人聊天。')
        if body.archived:
            if db.execute(
                "SELECT 1 FROM accord_runs WHERE thread_id=? AND status IN ('queued','running')",
                (tid,),
            ).fetchone():
                raise DomainError(409, '请先停止当前回答。')
            db.execute(
                'INSERT OR IGNORE INTO accord_thread_archives VALUES(?,?,?)',
                (uid, tid, store.now()),
            )
        else:
            db.execute(
                'DELETE FROM accord_thread_archives WHERE owner_id=? AND thread_id=?', (uid, tid)
            )
        return {'archived': body.archived}

    return operate(uid, body, 'thread:archive:' + tid, run)
