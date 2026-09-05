"""Private exploration, immutable submissions, atomic release, and human decisions."""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from . import access, context, handoffs, store, workspace
from .auth import principal
from .commands import Operation, VersionedOperation, expect, operate, text

router = APIRouter(prefix='/api/topics')


class NewTopic(Operation):
    title: str = Field(min_length=1, max_length=100)
    brief: str = Field(min_length=1, max_length=8000)
    member_ids: list[str] = Field(min_length=1, max_length=30)
    source_ids: list[str] = Field(default_factory=list, max_length=10)
    deadline: str = Field(default='', max_length=50)


class Exploration(Operation):
    title: str = Field(default='新的方向', min_length=1, max_length=100)
    folder_id: str = Field(default='', max_length=100)


class Submission(VersionedOperation):
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=12000)
    source_ids: list[str] = Field(default_factory=list, max_length=10)


class Decision(VersionedOperation):
    body: str = Field(min_length=1, max_length=4000)
    proposal_ids: list[str] = Field(min_length=1, max_length=30)


class Handoff(Operation):
    target_id: str
    task_title: str = Field(min_length=1, max_length=160)


def members(db, rid):
    return [r['member_id'] for r in db.execute('SELECT member_id FROM accord_round_members WHERE round_id=? ORDER BY rowid', (rid,))]


def summary(db, uid, row):
    own = db.execute('SELECT * FROM accord_submissions WHERE round_id=? AND member_id=?', (row['id'], uid)).fetchone()
    count = db.execute("SELECT count(*) FROM accord_submissions WHERE round_id=? AND proposal_id!=''", (row['id'],)).fetchone()[0]
    return {**dict(row), 'member_ids': members(db, row['id']), 'submitted_count': count,
        'my_submitted': bool(own and own['proposal_id']), 'submission_version': own['version'] if own else 0}


def list_rounds(db, uid):
    return [summary(db, uid, row) for row in db.execute('''SELECT r.* FROM accord_rounds r JOIN accord_round_members m
        ON m.round_id=r.id WHERE m.member_id=? ORDER BY r.created_at DESC''', (uid,)).fetchall()]


def ensure_stage(round_, stage):
    if round_['stage'] != stage:
        raise HTTPException(409, '课题阶段已改变，请刷新后继续。输入已保留。')


def host(round_, uid):
    if round_['owner_id'] != uid:
        raise HTTPException(403, '需要本轮主持人操作。')


def shared_refs(db, uid, source_ids, audience):
    refs = []
    neutral = {'id': '', 'owner_id': uid, 'target_id': uid, 'kind': 'workspace', 'purpose': 'ordinary', 'round_id': ''}
    all_refs = context.expand(db, uid, neutral, [{'id': rid} for rid in dict.fromkeys(source_ids)])
    for ref in all_refs:
        resource = access.resource_for(db, uid, ref['id'], ref['version'])
        if not all(access.can_read(db, member, resource) for member in audience):
            raise HTTPException(403, '引用中有参与者无权读取的资料，请移除后再提交。')
        if ref['id'] in source_ids:
            refs.append({'id': ref['id'], 'version': ref['version']})
    return refs


@router.post('')
def create_topic(body: NewTopic, uid=Depends(principal)):
    def run(db):
        audience = list(dict.fromkeys([uid] + body.member_ids))
        if len(audience) < 2:
            raise HTTPException(422, '请选择至少一位同事。')
        if any(not db.execute('SELECT 1 FROM accord_accounts WHERE unit_id=?', (member,)).fetchone() for member in audience):
            raise HTTPException(404, '参与者不存在。')
        deadline = ''
        if body.deadline:
            try:
                date = datetime.fromisoformat(body.deadline.replace('Z', '+00:00'))
                if date.tzinfo is None or date <= datetime.now(timezone.utc):
                    raise ValueError()
                deadline = date.astimezone(timezone.utc).isoformat()
            except ValueError:
                raise HTTPException(422, '请选择未来的截止时间。')
        refs = shared_refs(db, uid, body.source_ids, audience)
        rid = store.new_id('round')
        brief_id = context.create_resource(db, uid, text(body.title)+' · 共同简报', text(body.brief), 'round', 'brief', rid, refs)
        db.execute('INSERT INTO accord_rounds(id,title,owner_id,brief_id,deadline,created_at) VALUES(?,?,?,?,?,?)',
            (rid, text(body.title), uid, brief_id, deadline, store.now()))
        db.executemany('INSERT INTO accord_round_members VALUES(?,?)', [(rid, member) for member in audience])
        return {'id': rid}
    return operate(uid, body, 'topic:create', run)


@router.get('/{rid}')
def topic(rid: str, uid=Depends(principal)):
    with store._lock:
        db = store._conn
        round_ = access.round_for(db, uid, rid)
        result = summary(db, uid, round_)
        result['brief'] = context.public_resource(access.resource_for(db, uid, round_['brief_id'], 1))
        own = db.execute('SELECT p.* FROM accord_proposals p JOIN accord_submissions s ON p.id=s.proposal_id WHERE s.round_id=? AND s.member_id=?', (rid, uid)).fetchone()
        result['my_submission'] = {**dict(own), 'sources': json.loads(own['sources'])} if own else None
        result['progress'] = []
        for member in result['member_ids']:
            submitted = db.execute("SELECT 1 FROM accord_submissions WHERE round_id=? AND member_id=? AND proposal_id!=''", (rid, member)).fetchone()
            explored = db.execute("SELECT 1 FROM accord_thread_scopes s JOIN accord_threads t ON t.id=s.thread_id WHERE s.round_id=? AND s.purpose='exploration' AND t.owner_id=?", (rid, member)).fetchone()
            result['progress'].append({'member_id': member, 'status': 'submitted' if submitted else 'exploring' if explored else 'not_started'})
        result['explorations'] = [access.thread_for(uid, row['id'], db) for row in db.execute("SELECT t.id FROM accord_threads t JOIN accord_thread_scopes s ON t.id=s.thread_id WHERE s.round_id=? AND t.owner_id=? AND s.purpose='exploration' ORDER BY t.updated_at DESC", (rid, uid)).fetchall()]
        result['proposals'] = []
        for release in db.execute('SELECT r.*,p.author_id,p.version AS proposal_version FROM accord_releases r JOIN accord_proposals p ON p.id=r.proposal_id WHERE r.round_id=? ORDER BY r.created_at,r.rowid', (rid,)):
            result['proposals'].append({**context.public_resource(access.resource_for(db, uid, release['resource_id'], 1)),
                'proposal_id': release['proposal_id'], 'author_id': release['author_id'], 'proposal_version': release['proposal_version']})
        result['decision'] = context.public_resource(access.resource_for(db, uid, round_['decision_id'], 1)) if round_['decision_id'] else None
        result['handoffs'] = [dict(row) for row in db.execute('''SELECT h.target_id,h.thread_id,t.status FROM accord_decision_handoffs h
            JOIN accord_threads t ON t.id=h.thread_id WHERE h.round_id=?''', (rid,))]
        return result


@router.post('/{rid}/explorations')
def explore(rid: str, body: Exploration, uid=Depends(principal)):
    def run(db):
        round_ = access.round_for(db, uid, rid)
        if body.folder_id:
            workspace.folder_for(db, uid, body.folder_id)
        tid, now = store.new_id('thread'), store.now()
        db.execute('INSERT INTO accord_threads(id,owner_id,target_id,title,kind,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
            (tid, uid, uid, text(body.title), 'workspace', now, now))
        db.execute('INSERT INTO accord_thread_scopes VALUES(?,?,?)', (tid, 'exploration', round_['id']))
        if body.folder_id:
            db.execute('INSERT INTO accord_placements VALUES(?,?,?,1)', (uid, tid, body.folder_id))
        return {'id': tid}
    return operate(uid, body, 'topic:explore:'+rid, run)


@router.post('/{rid}/submit')
def submit(rid: str, body: Submission, uid=Depends(principal)):
    def run(db):
        round_ = access.round_for(db, uid, rid)
        ensure_stage(round_, 'exploring')
        old = db.execute('SELECT * FROM accord_submissions WHERE round_id=? AND member_id=?', (rid, uid)).fetchone()
        revision = old['version'] if old else 0
        expect(revision, body.expected_version)
        refs = shared_refs(db, uid, body.source_ids, members(db, rid))
        number = db.execute('SELECT coalesce(max(version),0)+1 FROM accord_proposals WHERE round_id=? AND author_id=?', (rid, uid)).fetchone()[0]
        pid = store.new_id('proposal')
        db.execute('INSERT INTO accord_proposals VALUES(?,?,?,?,?,?,?,?)', (pid, rid, uid, number, text(body.title), text(body.body), json.dumps(refs), store.now()))
        db.execute('''INSERT INTO accord_submissions VALUES(?,?,?,?) ON CONFLICT(round_id,member_id)
            DO UPDATE SET proposal_id=excluded.proposal_id,version=excluded.version''', (rid, uid, pid, revision+1))
        db.execute('UPDATE accord_rounds SET version=version+1 WHERE id=?', (rid,))
        return {'id': pid, 'version': number, 'submission_version': revision+1}
    return operate(uid, body, 'topic:submit:'+rid, run)


@router.post('/{rid}/withdraw')
def withdraw(rid: str, body: VersionedOperation, uid=Depends(principal)):
    def run(db):
        round_ = access.round_for(db, uid, rid)
        ensure_stage(round_, 'exploring')
        old = db.execute('SELECT * FROM accord_submissions WHERE round_id=? AND member_id=?', (rid, uid)).fetchone()
        expect(old['version'] if old else 0, body.expected_version)
        if not old or not old['proposal_id']:
            raise HTTPException(409, '当前没有待公开的提交。')
        db.execute("UPDATE accord_submissions SET proposal_id='',version=version+1 WHERE round_id=? AND member_id=?", (rid, uid))
        db.execute('UPDATE accord_rounds SET version=version+1 WHERE id=?', (rid,))
        return {'submission_version': old['version']+1}
    return operate(uid, body, 'topic:withdraw:'+rid, run)


@router.post('/{rid}/release')
def release(rid: str, body: VersionedOperation, uid=Depends(principal)):
    def run(db):
        round_ = access.round_for(db, uid, rid)
        host(round_, uid); ensure_stage(round_, 'exploring'); expect(round_['version'], body.expected_version)
        proposals = db.execute('''SELECT p.* FROM accord_proposals p JOIN accord_submissions s ON s.proposal_id=p.id WHERE s.round_id=? ORDER BY p.created_at''', (rid,)).fetchall()
        if not proposals:
            raise HTTPException(422, '还没有可以公开的方案。')
        audience = members(db, rid)
        for p in proposals:
            refs = json.loads(p['sources'])
            for member in audience:
                try:
                    context.expand(db, p['author_id'], {'owner_id': p['author_id'], 'target_id': member, 'kind': 'peer', 'purpose': 'ordinary'}, refs)
                except HTTPException:
                    raise HTTPException(409, '提交所引用的资料权限发生变化，请作者更新提交。')
            resource_id = context.create_resource(db, p['author_id'], p['title'], p['body'], 'round', 'proposal', rid, refs)
            db.execute('INSERT INTO accord_releases VALUES(?,?,?,?)', (rid, p['id'], resource_id, store.now()))
        db.execute("UPDATE accord_rounds SET stage='reviewing',version=version+1 WHERE id=?", (rid,))
        return {'stage': 'reviewing', 'released': len(proposals)}
    return operate(uid, body, 'topic:release:'+rid, run)


@router.post('/{rid}/reviews')
def review(rid: str, body: Operation, uid=Depends(principal)):
    def run(db):
        round_ = access.round_for(db, uid, rid)
        if round_['stage'] == 'exploring':
            raise HTTPException(409, '请等待方案统一公开。')
        old = db.execute("SELECT t.id FROM accord_threads t JOIN accord_thread_scopes s ON s.thread_id=t.id WHERE s.round_id=? AND s.purpose='review' AND t.owner_id=?", (rid, uid)).fetchone()
        if old:
            return {'id': old['id']}
        tid, now = store.new_id('thread'), store.now()
        db.execute('INSERT INTO accord_threads(id,owner_id,target_id,title,kind,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
            (tid, uid, uid, round_['title']+' · 比较方案', 'workspace', now, now))
        db.execute('INSERT INTO accord_thread_scopes VALUES(?,?,?)', (tid, 'review', rid))
        return {'id': tid}
    return operate(uid, body, 'topic:review:'+rid, run)


@router.post('/{rid}/decision')
def decide(rid: str, body: Decision, uid=Depends(principal)):
    def run(db):
        round_ = access.round_for(db, uid, rid)
        host(round_, uid); ensure_stage(round_, 'reviewing'); expect(round_['version'], body.expected_version)
        released = {row['proposal_id']: row['resource_id'] for row in db.execute('SELECT * FROM accord_releases WHERE round_id=?', (rid,))}
        if not set(body.proposal_ids) <= released.keys():
            raise HTTPException(404, '只能选择本轮已公开的方案。')
        refs = [{'id': released[pid], 'version': 1} for pid in dict.fromkeys(body.proposal_ids)]
        decision_id = context.create_resource(db, uid, round_['title']+' · 决策', text(body.body), 'round', 'decision', rid, refs)
        db.execute("UPDATE accord_rounds SET stage='decided',decision_id=?,version=version+1 WHERE id=?", (decision_id, rid))
        return {'stage': 'decided', 'decision_id': decision_id}
    return operate(uid, body, 'topic:decision:'+rid, run)


@router.post('/{rid}/handoff')
def handoff(rid: str, body: Handoff, uid=Depends(principal)):
    def run(db):
        round_ = access.round_for(db, uid, rid)
        host(round_, uid); ensure_stage(round_, 'decided')
        access.round_for(db, body.target_id, rid)
        old = db.execute('SELECT thread_id FROM accord_decision_handoffs WHERE round_id=? AND target_id=?', (rid, body.target_id)).fetchone()
        if old:
            return {'id': old['thread_id']}
        decision = access.resource_for(db, uid, round_['decision_id'], 1)
        tid = handoffs.create(db, uid, body.target_id, text(body.task_title), decision['body'], [{'id': decision['id'], 'version': 1}], rid)
        db.execute('INSERT INTO accord_decision_handoffs VALUES(?,?,?)', (rid, body.target_id, tid))
        return {'id': tid}
    return operate(uid, body, 'topic:handoff:'+rid, run)
