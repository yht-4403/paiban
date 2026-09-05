"""Personal folders, resource collections, and context bindings."""
import hashlib
import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field

from . import access, context, handoffs, store
from .auth import principal
from .commands import Operation, VersionedOperation, expect, operate, text

router = APIRouter(prefix='/api')


class NewFolder(Operation):
    name: str = Field(min_length=1, max_length=60)


class RenameFolder(VersionedOperation):
    name: str = Field(min_length=1, max_length=60)


class Move(VersionedOperation):
    folder_id: str = Field(default='', max_length=100)


class Bindings(VersionedOperation):
    included: list[str] = Field(default_factory=list, max_length=20)
    excluded: list[str] = Field(default_factory=list, max_length=20)
    folder_ids: Optional[list[str]] = Field(default=None, max_length=8)


class Resource(Operation):
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(default='', max_length=16000)
    scope: Literal['private', 'team'] = 'private'
    resource_ids: list[str] = Field(default_factory=list, max_length=12)


class ResourceEdit(Resource):
    expected_version: int = Field(ge=1)


class Share(Operation):
    target_id: str
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=8000)
    source_ids: list[str] = Field(default_factory=list, max_length=12)


def folder_for(db, uid, fid):
    row = db.execute('SELECT * FROM accord_folders WHERE id=? AND owner_id=?', (fid, uid)).fetchone()
    if not row:
        raise HTTPException(404, '文件夹不存在。')
    return dict(row)


def folders(db, uid):
    return [{**dict(row), 'binding': context.binding(db, uid, 'folder', row['id'])} for row in db.execute('SELECT * FROM accord_folders WHERE owner_id=? ORDER BY created_at,id', (uid,))]


@router.post('/folders')
def new_folder(body: NewFolder, uid=Depends(principal)):
    def run(db):
        if db.execute('SELECT count(*) FROM accord_folders WHERE owner_id=?', (uid,)).fetchone()[0] >= 100:
            raise HTTPException(422, '文件夹已达到上限，请先整理现有目录。')
        fid = store.new_id('folder')
        db.execute('INSERT INTO accord_folders(id,owner_id,name,created_at) VALUES(?,?,?,?)', (fid, uid, text(body.name), store.now()))
        return {'id': fid, 'version': 1}
    return operate(uid, body, 'folder:create', run)


@router.post('/folders/{fid}/rename')
def rename_folder(fid: str, body: RenameFolder, uid=Depends(principal)):
    def run(db):
        folder = folder_for(db, uid, fid)
        expect(folder['version'], body.expected_version)
        db.execute('UPDATE accord_folders SET name=?,version=version+1 WHERE id=?', (text(body.name), fid))
        return {'version': folder['version']+1}
    return operate(uid, body, 'folder:rename:'+fid, run)


@router.post('/folders/{fid}/remove')
def remove_folder(fid: str, body: VersionedOperation, uid=Depends(principal)):
    def run(db):
        folder = folder_for(db, uid, fid)
        expect(folder['version'], body.expected_version)
        if db.execute('SELECT 1 FROM accord_placements WHERE owner_id=? AND folder_id=?', (uid, fid)).fetchone():
            raise HTTPException(409, '请先移出文件夹内的聊天。')
        if db.execute('SELECT 1 FROM accord_context_folders WHERE owner_id=? AND folder_id=?', (uid, fid)).fetchone():
            raise HTTPException(409, '请先从会话资料区移除这个文件夹。')
        db.execute('DELETE FROM accord_bindings WHERE owner_id=? AND target_kind=? AND target_id=?', (uid, 'folder', fid))
        db.execute('DELETE FROM accord_folders WHERE id=?', (fid,))
        return {'removed': True}
    return operate(uid, body, 'folder:remove:'+fid, run)


@router.post('/threads/{tid}/move')
def move_thread(tid: str, body: Move, uid=Depends(principal)):
    def run(db):
        thread = access.thread_for(uid, tid, db)
        expect(thread['placement_version'], body.expected_version)
        if body.folder_id:
            folder_for(db, uid, body.folder_id)
        version = thread['placement_version']+1
        db.execute('''INSERT INTO accord_placements VALUES(?,?,?,?) ON CONFLICT(owner_id,thread_id)
            DO UPDATE SET folder_id=excluded.folder_id,version=excluded.version''', (uid, tid, body.folder_id, version))
        return {'folder_id': body.folder_id, 'version': version}
    return operate(uid, body, 'thread:move:'+tid, run)


def update_bindings(db, uid, kind, target, body):
    if kind == 'folder':
        folder_for(db, uid, target)
        thread = None
    else:
        thread = access.thread_for(uid, target, db)
        if thread['owner_id'] != uid or thread['status'] != 'agent':
            raise HTTPException(403, '当前会话不能调整 AI 资料。')
    current = context.binding(db, uid, kind, target)
    expect(current['version'], body.expected_version)
    if body.folder_ids:
        if kind != 'thread':
            raise HTTPException(422, '请将文件夹加入会话资料区。')
        for fid in set(body.folder_ids):
            folder_for(db, uid, fid)
    for rid in set(body.included + body.excluded):
        resource = access.resource_for(db, uid, rid)
        if thread and not access.compatible(db, thread, resource):
            raise HTTPException(403, '这份资料不适用于当前协作范围。')
    context.put_binding(db, uid, kind, target, body.included, body.excluded, current['version']+1, body.folder_ids)
    return {'version': current['version']+1}


@router.post('/folders/{fid}/bindings')
def folder_bindings(fid: str, body: Bindings, uid=Depends(principal)):
    return operate(uid, body, 'folder:bindings:'+fid, lambda db: update_bindings(db, uid, 'folder', fid, body))


@router.post('/threads/{tid}/bindings')
def thread_bindings(tid: str, body: Bindings, uid=Depends(principal)):
    return operate(uid, body, 'thread:bindings:'+tid, lambda db: update_bindings(db, uid, 'thread', tid, body))


@router.get('/threads/{tid}/context')
def thread_context(tid: str, uid=Depends(principal)):
    with store._lock:
        thread = access.thread_for(uid, tid, store._conn)
        return {**context.effective(store._conn, uid, thread), 'available': context.available(store._conn, uid, thread, False)}


def resource_refs(db, uid, body):
    if not body.body.strip() and not body.resource_ids:
        raise HTTPException(422, '请填写正文或选择资料。')
    refs = []
    for rid in dict.fromkeys(body.resource_ids):
        resource = access.resource_for(db, uid, rid)
        if body.scope == 'team' and resource['scope'] != 'team':
            raise HTTPException(403, '团队资料集合只能引用已向团队共享的资料。')
        refs.append({'id': rid, 'version': resource['version']})
    return refs


@router.post('/resources')
def create_resource(body: Resource, uid=Depends(principal)):
    def run(db):
        refs = resource_refs(db, uid, body)
        rid = context.create_resource(db, uid, text(body.title), body.body.strip(), body.scope, 'collection' if refs else 'note', refs=refs)
        return {'id': rid, 'version': 1}
    return operate(uid, body, 'resource:create', run)


@router.post('/resources/{rid}/update')
def update_resource(rid: str, body: ResourceEdit, uid=Depends(principal)):
    def run(db):
        resource = access.resource_for(db, uid, rid)
        if resource['owner_id'] != uid or resource['kind'] not in ('note', 'collection'):
            raise HTTPException(403, '这份资料需要通过所属工作流程更新。')
        expect(resource['version'], body.expected_version)
        if rid in body.resource_ids:
            raise HTTPException(422, '资料不能引用自己。')
        refs = resource_refs(db, uid, body)
        version = resource['version']+1
        db.execute('INSERT INTO accord_resource_versions VALUES(?,?,?,?,?,?,?)', (rid, version, text(body.title), body.body.strip(), json.dumps(refs),
            hashlib.sha256((body.body + json.dumps(refs, sort_keys=True)).encode()).hexdigest(), store.now()))
        db.execute('UPDATE accord_resources SET version=?,scope=?,kind=? WHERE id=?', (version, body.scope, 'collection' if refs else 'note', rid))
        return {'id': rid, 'version': version}
    return operate(uid, body, 'resource:update:'+rid, run)


@router.get('/resources/{rid}')
def read_resource(rid: str, version: Optional[int] = Query(default=None, ge=1), uid=Depends(principal)):
    with store._lock:
        return context.public_resource(access.resource_for(store._conn, uid, rid, version))


@router.post('/threads/{tid}/share')
def share(tid: str, body: Share, uid=Depends(principal)):
    def run(db):
        thread = access.thread_for(uid, tid, db)
        if thread['owner_id'] != uid or thread['purpose'] != 'ordinary' or thread['kind'] != 'workspace':
            raise HTTPException(403, '这段会话请使用所属流程的提交或交接操作。')
        refs = [{'id': rid} for rid in body.source_ids]
        return {'id': handoffs.create(db, uid, body.target_id, text(body.title), text(body.body), refs)}
    return operate(uid, body, 'thread:share:'+tid, run)
