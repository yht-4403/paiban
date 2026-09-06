import json
from datetime import datetime, timezone

from accord_api.modules import knowledge as context
from accord_api.modules.collaboration import handoffs as handoffs
from accord_api.modules.identity import service as identity
from accord_api.modules.permissions import policy as access
from accord_api.modules.topics.schemas import (
    Decision,
    Direction,
    Exploration,
    Handoff,
    NewTopic,
    Submission,
)
from accord_api.modules.workspace import service as workspace
from accord_api.platform.commands import Operation, VersionedOperation, expect, operate, text
from accord_api.platform.db import database as store
from accord_api.platform.errors import DomainError


def members(db, rid):
    return [
        r['member_id']
        for r in db.execute(
            'SELECT member_id FROM accord_round_members WHERE round_id=? ORDER BY rowid', (rid,)
        )
    ]


def visible_task_ids(db, rid, uid):
    return [
        row['task_id']
        for row in db.execute(
            """SELECT l.task_id FROM accord_task_topics l
            JOIN tasks t ON t.id=l.task_id
            JOIN accord_task_acl a ON a.task_id=t.id
            WHERE l.round_id=? AND (t.assignee_id=? OR a.creator_id=?)
            ORDER BY t.created_at,t.rowid""",
            (rid, uid, uid),
        )
    ]


def _round_projection(db, uid, row):
    member_ids = members(db, row['id'])
    submitted_count = db.execute(
        "SELECT count(*) FROM accord_submissions WHERE round_id=? AND proposal_id!=''",
        (row['id'],),
    ).fetchone()[0]
    direction_count = db.execute(
        'SELECT count(*) FROM accord_releases WHERE round_id=?', (row['id'],)
    ).fetchone()[0]
    public_direction_count = db.execute(
        'SELECT count(*) FROM accord_round_directions WHERE round_id=?', (row['id'],)
    ).fetchone()[0]
    all_submitted = bool(member_ids) and submitted_count == len(member_ids)
    if row['stage'] == 'decided':
        completion_state = 'decided'
        attention = 'results_available'
    elif row['stage'] == 'reviewing':
        completion_state = 'reviewing'
        attention = 'needs_decision' if row['owner_id'] == uid else 'results_available'
    elif all_submitted:
        completion_state = 'ready_for_review'
        attention = 'ready_to_release' if row['owner_id'] == uid else 'waiting_for_release'
    else:
        completion_state = 'in_progress'
        attention = 'in_progress'
    fixture = db.execute(
        "SELECT 1 FROM accord_task_topics WHERE round_id=? AND origin='tutorial_fixture' LIMIT 1",
        (row['id'],),
    ).fetchone()
    return {
        'task_type': 'exploration',
        'task_ids': visible_task_ids(db, row['id'], uid),
        'stage': row['stage'],
        'member_ids': member_ids,
        'member_count': len(member_ids),
        'submitted_count': submitted_count,
        'direction_count': direction_count,
        'public_direction_count': public_direction_count,
        'all_submitted': all_submitted,
        'completion_state': completion_state,
        'attention': attention,
        'ready_to_release': attention == 'ready_to_release',
        'needs_decision': attention == 'needs_decision',
        'results_available': row['stage'] in ('reviewing', 'decided'),
        'is_highlighted': all_submitted or row['stage'] in ('reviewing', 'decided'),
        'origin': 'tutorial_fixture' if fixture else 'live',
        'is_fixture': bool(fixture),
    }


def summary(db, uid, row):
    own = db.execute(
        'SELECT * FROM accord_submissions WHERE round_id=? AND member_id=?', (row['id'], uid)
    ).fetchone()
    projection = _round_projection(db, uid, row)
    return {
        **dict(row),
        **projection,
        'my_submitted': bool(own and own['proposal_id']),
        'submission_version': own['version'] if own else 0,
    }


def task_projection(db, uid, task):
    item = dict(task)
    link = db.execute(
        'SELECT round_id,origin FROM accord_task_topics WHERE task_id=?', (item['id'],)
    ).fetchone()
    if not link:
        return {**item, 'task_type': 'normal', 'topic_id': '', 'exploration': None}
    round_ = access.round_for(db, uid, link['round_id'])
    projection = _round_projection(db, uid, round_)
    return {
        **item,
        'task_type': 'exploration',
        'topic_id': link['round_id'],
        'exploration': {
            key: projection[key]
            for key in (
                'stage',
                'completion_state',
                'submitted_count',
                'member_count',
                'direction_count',
                'public_direction_count',
                'all_submitted',
                'attention',
                'ready_to_release',
                'needs_decision',
                'results_available',
                'is_highlighted',
                'origin',
                'is_fixture',
            )
        },
    }


def list_rounds(db, uid):
    return [
        summary(db, uid, row)
        for row in db.execute(
            """SELECT r.* FROM accord_rounds r JOIN accord_round_members m
        ON m.round_id=r.id WHERE m.member_id=? ORDER BY r.created_at DESC""",
            (uid,),
        ).fetchall()
        if identity.shares_account_roster(uid, row['owner_id'])
    ]


def ensure_stage(round_, stage):
    if round_['stage'] != stage:
        raise DomainError(409, '课题阶段已改变，请刷新后继续。输入已保留。')


def ensure_mutable(db, rid):
    fixture = db.execute(
        "SELECT 1 FROM accord_task_topics WHERE round_id=? AND origin='tutorial_fixture' LIMIT 1",
        (rid,),
    ).fetchone()
    if fixture:
        raise DomainError(409, '这是只读的创新探索虚拟实例，可从教学入口重置。')


def host(round_, uid):
    if round_['owner_id'] != uid:
        raise DomainError(403, '需要本轮主持人操作。')


def shared_refs(db, uid, source_ids, audience):
    refs = []
    neutral = {
        'id': '',
        'owner_id': uid,
        'target_id': uid,
        'kind': 'workspace',
        'purpose': 'ordinary',
        'round_id': '',
    }
    all_refs = context.expand(db, uid, neutral, [{'id': rid} for rid in dict.fromkeys(source_ids)])
    for ref in all_refs:
        resource = access.resource_for(db, uid, ref['id'], ref['version'])
        if not all(access.can_read(db, member, resource) for member in audience):
            raise DomainError(403, '引用中有参与者无权读取的资料，请移除后再提交。')
        if ref['id'] in source_ids:
            refs.append({'id': ref['id'], 'version': ref['version']})
    return refs


def create_round(db, uid, title, brief, member_ids, source_ids=None, deadline=''):
    audience = list(dict.fromkeys([uid, *member_ids]))
    if len(audience) < 2:
        raise DomainError(422, '请选择至少一位同事。')
    if any(
        not identity.shares_account_roster(uid, member)
        or not db.execute('SELECT 1 FROM accord_accounts WHERE unit_id=?', (member,)).fetchone()
        for member in audience
    ):
        raise DomainError(404, '参与者不存在。')
    normalized_deadline = ''
    if deadline:
        try:
            date = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
            if date.tzinfo is None or date <= datetime.now(timezone.utc):
                raise ValueError()
            normalized_deadline = date.astimezone(timezone.utc).isoformat()
        except ValueError:
            raise DomainError(422, '请选择未来的截止时间。')
    refs = shared_refs(db, uid, source_ids or [], audience)
    rid = store.new_id('round')
    brief_id = context.create_resource(
        db, uid, text(title) + ' · 共同简报', text(brief), 'round', 'brief', rid, refs
    )
    db.execute(
        'INSERT INTO accord_rounds(id,title,owner_id,brief_id,deadline,created_at) VALUES(?,?,?,?,?,?)',
        (rid, text(title), uid, brief_id, normalized_deadline, store.now()),
    )
    db.executemany(
        'INSERT INTO accord_round_members VALUES(?,?)', [(rid, member) for member in audience]
    )
    return rid


def create_topic(*, body: NewTopic, uid):
    def run(db):
        return {
            'id': create_round(
                db,
                uid,
                body.title,
                body.brief,
                body.member_ids,
                body.source_ids,
                body.deadline,
            )
        }

    return operate(uid, body, 'topic:create', run)


def topic(*, rid: str, uid):
    with store.lock:
        db = store.connection()
        round_ = access.round_for(db, uid, rid)
        result = summary(db, uid, round_)
        result['brief'] = context.public_resource(
            access.resource_for(db, uid, round_['brief_id'], 1)
        )
        own = db.execute(
            'SELECT p.* FROM accord_proposals p JOIN accord_submissions s ON p.id=s.proposal_id WHERE s.round_id=? AND s.member_id=?',
            (rid, uid),
        ).fetchone()
        result['my_submission'] = (
            {**dict(own), 'sources': json.loads(own['sources'])} if own else None
        )
        result['progress'] = []
        for member in result['member_ids']:
            submitted = db.execute(
                "SELECT 1 FROM accord_submissions WHERE round_id=? AND member_id=? AND proposal_id!=''",
                (rid, member),
            ).fetchone()
            explored = db.execute(
                "SELECT 1 FROM accord_thread_scopes s JOIN accord_threads t ON t.id=s.thread_id WHERE s.round_id=? AND s.purpose='exploration' AND t.owner_id=?",
                (rid, member),
            ).fetchone()
            result['progress'].append(
                {
                    'member_id': member,
                    'status': 'submitted'
                    if submitted
                    else 'exploring'
                    if explored
                    else 'not_started',
                }
            )
        result['explorations'] = [
            access.thread_for(uid, row['id'], db)
            for row in db.execute(
                "SELECT t.id FROM accord_threads t JOIN accord_thread_scopes s ON t.id=s.thread_id WHERE s.round_id=? AND t.owner_id=? AND s.purpose='exploration' ORDER BY t.updated_at DESC",
                (rid, uid),
            ).fetchall()
        ]
        result['directions'] = [
            dict(direction)
            for direction in db.execute(
                'SELECT member_id,label,version,updated_at FROM accord_round_directions WHERE round_id=? ORDER BY rowid',
                (rid,),
            )
        ]
        result['proposals'] = []
        for release in db.execute(
            'SELECT r.*,p.author_id,p.version AS proposal_version FROM accord_releases r JOIN accord_proposals p ON p.id=r.proposal_id WHERE r.round_id=? ORDER BY r.created_at,r.rowid',
            (rid,),
        ):
            result['proposals'].append(
                {
                    **context.public_resource(
                        access.resource_for(db, uid, release['resource_id'], 1)
                    ),
                    'proposal_id': release['proposal_id'],
                    'author_id': release['author_id'],
                    'proposal_version': release['proposal_version'],
                }
            )
        result['decision'] = (
            context.public_resource(access.resource_for(db, uid, round_['decision_id'], 1))
            if round_['decision_id']
            else None
        )
        result['handoffs'] = [
            dict(row)
            for row in db.execute(
                """SELECT h.target_id,h.thread_id,t.status FROM accord_decision_handoffs h
            JOIN accord_threads t ON t.id=h.thread_id WHERE h.round_id=?""",
                (rid,),
            )
        ]
        return result


def exploration_task(*, task_id: str, uid):
    with store.lock:
        db = store.connection()
        task = db.execute(
            """SELECT t.*,a.creator_id,a.thread_id FROM tasks t
            JOIN accord_task_acl a ON a.task_id=t.id WHERE t.id=?""",
            (task_id,),
        ).fetchone()
        if (
            not task
            or uid not in (task['assignee_id'], task['creator_id'])
            or not identity.shares_account_roster(task['creator_id'], task['assignee_id'])
        ):
            raise DomainError(404, '探索任务不存在或你没有查看权限。')
        link = db.execute(
            'SELECT round_id FROM accord_task_topics WHERE task_id=?', (task_id,)
        ).fetchone()
        if not link:
            raise DomainError(404, '探索任务不存在或你没有查看权限。')
        access.round_for(db, uid, link['round_id'])
        return {
            'task': task_projection(db, uid, task),
            'topic': topic(rid=link['round_id'], uid=uid),
        }


def create_exploration(db, rid, uid, title, folder_id=''):
    round_ = access.round_for(db, uid, rid)
    ensure_mutable(db, rid)
    if folder_id:
        workspace.folder_for(db, uid, folder_id)
    tid, now = store.new_id('thread'), store.now()
    db.execute(
        'INSERT INTO accord_threads(id,owner_id,target_id,title,kind,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
        (tid, uid, uid, text(title), 'workspace', now, now),
    )
    db.execute('INSERT INTO accord_thread_scopes VALUES(?,?,?)', (tid, 'exploration', round_['id']))
    if folder_id:
        db.execute('INSERT INTO accord_placements VALUES(?,?,?,1)', (uid, tid, folder_id))
    return tid


def explore(*, rid: str, body: Exploration, uid):
    def run(db):
        return {'id': create_exploration(db, rid, uid, body.title, body.folder_id)}

    return operate(uid, body, 'topic:explore:' + rid, run)


def direction(*, rid: str, body: Direction, uid):
    def run(db):
        round_ = access.round_for(db, uid, rid)
        ensure_mutable(db, rid)
        ensure_stage(round_, 'exploring')
        old = db.execute(
            'SELECT version FROM accord_round_directions WHERE round_id=? AND member_id=?',
            (rid, uid),
        ).fetchone()
        version = old['version'] if old else 0
        expect(version, body.expected_version)
        db.execute(
            """INSERT INTO accord_round_directions(round_id,member_id,label,version,updated_at)
            VALUES(?,?,?,?,?) ON CONFLICT(round_id,member_id) DO UPDATE SET
            label=excluded.label,version=excluded.version,updated_at=excluded.updated_at""",
            (rid, uid, text(body.label), version + 1, store.now()),
        )
        db.execute('UPDATE accord_rounds SET version=version+1 WHERE id=?', (rid,))
        return {'member_id': uid, 'label': text(body.label), 'version': version + 1}

    return operate(uid, body, 'topic:direction:' + rid, run)


def submit(*, rid: str, body: Submission, uid):
    def run(db):
        round_ = access.round_for(db, uid, rid)
        ensure_mutable(db, rid)
        ensure_stage(round_, 'exploring')
        old = db.execute(
            'SELECT * FROM accord_submissions WHERE round_id=? AND member_id=?', (rid, uid)
        ).fetchone()
        revision = old['version'] if old else 0
        expect(revision, body.expected_version)
        refs = shared_refs(db, uid, body.source_ids, members(db, rid))
        number = db.execute(
            'SELECT coalesce(max(version),0)+1 FROM accord_proposals WHERE round_id=? AND author_id=?',
            (rid, uid),
        ).fetchone()[0]
        pid = store.new_id('proposal')
        db.execute(
            'INSERT INTO accord_proposals VALUES(?,?,?,?,?,?,?,?)',
            (
                pid,
                rid,
                uid,
                number,
                text(body.title),
                text(body.body),
                json.dumps(refs),
                store.now(),
            ),
        )
        db.execute(
            """INSERT INTO accord_submissions VALUES(?,?,?,?) ON CONFLICT(round_id,member_id)
            DO UPDATE SET proposal_id=excluded.proposal_id,version=excluded.version""",
            (rid, uid, pid, revision + 1),
        )
        linked = db.execute(
            """SELECT t.id FROM tasks t JOIN accord_task_topics l ON l.task_id=t.id
            WHERE l.round_id=? AND l.member_id=? AND t.assignee_id=?""",
            (rid, uid, uid),
        ).fetchone()
        if linked:
            db.execute(
                "UPDATE tasks SET status='done',artifact=?,updated_at=? WHERE id=?",
                ('已封存探索成果，等待统一公开。', store.now(), linked['id']),
            )
        db.execute('UPDATE accord_rounds SET version=version+1 WHERE id=?', (rid,))
        return {'id': pid, 'version': number, 'submission_version': revision + 1}

    return operate(uid, body, 'topic:submit:' + rid, run)


def withdraw(*, rid: str, body: VersionedOperation, uid):
    def run(db):
        round_ = access.round_for(db, uid, rid)
        ensure_mutable(db, rid)
        ensure_stage(round_, 'exploring')
        old = db.execute(
            'SELECT * FROM accord_submissions WHERE round_id=? AND member_id=?', (rid, uid)
        ).fetchone()
        expect(old['version'] if old else 0, body.expected_version)
        if not old or not old['proposal_id']:
            raise DomainError(409, '当前没有待公开的提交。')
        db.execute(
            "UPDATE accord_submissions SET proposal_id='',version=version+1 WHERE round_id=? AND member_id=?",
            (rid, uid),
        )
        db.execute(
            """UPDATE tasks SET status='open',artifact='',updated_at=? WHERE id IN (
            SELECT task_id FROM accord_task_topics WHERE round_id=? AND member_id=?)""",
            (store.now(), rid, uid),
        )
        db.execute('UPDATE accord_rounds SET version=version+1 WHERE id=?', (rid,))
        return {'submission_version': old['version'] + 1}

    return operate(uid, body, 'topic:withdraw:' + rid, run)


def release(*, rid: str, body: VersionedOperation, uid):
    def run(db):
        round_ = access.round_for(db, uid, rid)
        ensure_mutable(db, rid)
        host(round_, uid)
        ensure_stage(round_, 'exploring')
        expect(round_['version'], body.expected_version)
        linked_count = db.execute(
            'SELECT count(*) FROM accord_task_topics WHERE round_id=?', (rid,)
        ).fetchone()[0]
        submitted_count = db.execute(
            "SELECT count(*) FROM accord_submissions WHERE round_id=? AND proposal_id!=''",
            (rid,),
        ).fetchone()[0]
        if linked_count and submitted_count != linked_count:
            raise DomainError(409, '请等待全部探索成员封存成果后再统一公开。')
        proposals = db.execute(
            """SELECT p.* FROM accord_proposals p JOIN accord_submissions s ON s.proposal_id=p.id WHERE s.round_id=? ORDER BY p.created_at""",
            (rid,),
        ).fetchall()
        if not proposals:
            raise DomainError(422, '还没有可以公开的方案。')
        audience = members(db, rid)
        for p in proposals:
            refs = json.loads(p['sources'])
            for member in audience:
                try:
                    context.expand(
                        db,
                        p['author_id'],
                        {
                            'owner_id': p['author_id'],
                            'target_id': member,
                            'kind': 'peer',
                            'purpose': 'ordinary',
                        },
                        refs,
                    )
                except DomainError:
                    raise DomainError(409, '提交所引用的资料权限发生变化，请作者更新提交。')
            resource_id = context.create_resource(
                db, p['author_id'], p['title'], p['body'], 'round', 'proposal', rid, refs
            )
            db.execute(
                'INSERT INTO accord_releases VALUES(?,?,?,?)',
                (rid, p['id'], resource_id, store.now()),
            )
        db.execute(
            "UPDATE accord_rounds SET stage='reviewing',version=version+1 WHERE id=?", (rid,)
        )
        return {'stage': 'reviewing', 'released': len(proposals)}

    return operate(uid, body, 'topic:release:' + rid, run)


def review(*, rid: str, body: Operation, uid):
    def run(db):
        round_ = access.round_for(db, uid, rid)
        ensure_mutable(db, rid)
        if round_['stage'] == 'exploring':
            raise DomainError(409, '请等待方案统一公开。')
        old = db.execute(
            "SELECT t.id FROM accord_threads t JOIN accord_thread_scopes s ON s.thread_id=t.id WHERE s.round_id=? AND s.purpose='review' AND t.owner_id=?",
            (rid, uid),
        ).fetchone()
        if old:
            return {'id': old['id']}
        tid, now = store.new_id('thread'), store.now()
        db.execute(
            'INSERT INTO accord_threads(id,owner_id,target_id,title,kind,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
            (tid, uid, uid, round_['title'] + ' · 比较方案', 'workspace', now, now),
        )
        db.execute('INSERT INTO accord_thread_scopes VALUES(?,?,?)', (tid, 'review', rid))
        return {'id': tid}

    return operate(uid, body, 'topic:review:' + rid, run)


def decide(*, rid: str, body: Decision, uid):
    def run(db):
        round_ = access.round_for(db, uid, rid)
        ensure_mutable(db, rid)
        host(round_, uid)
        ensure_stage(round_, 'reviewing')
        expect(round_['version'], body.expected_version)
        released = {
            row['proposal_id']: row['resource_id']
            for row in db.execute('SELECT * FROM accord_releases WHERE round_id=?', (rid,))
        }
        if not set(body.proposal_ids) <= released.keys():
            raise DomainError(404, '只能选择本轮已公开的方案。')
        refs = [{'id': released[pid], 'version': 1} for pid in dict.fromkeys(body.proposal_ids)]
        decision_id = context.create_resource(
            db, uid, round_['title'] + ' · 决策', text(body.body), 'round', 'decision', rid, refs
        )
        db.execute(
            "UPDATE accord_rounds SET stage='decided',decision_id=?,version=version+1 WHERE id=?",
            (decision_id, rid),
        )
        return {'stage': 'decided', 'decision_id': decision_id}

    return operate(uid, body, 'topic:decision:' + rid, run)


def handoff(*, rid: str, body: Handoff, uid):
    def run(db):
        round_ = access.round_for(db, uid, rid)
        ensure_mutable(db, rid)
        host(round_, uid)
        ensure_stage(round_, 'decided')
        access.round_for(db, body.target_id, rid)
        old = db.execute(
            'SELECT thread_id FROM accord_decision_handoffs WHERE round_id=? AND target_id=?',
            (rid, body.target_id),
        ).fetchone()
        if old:
            return {'id': old['thread_id']}
        decision = access.resource_for(db, uid, round_['decision_id'], 1)
        tid = handoffs.create(
            db,
            uid,
            body.target_id,
            text(body.task_title),
            decision['body'],
            [{'id': decision['id'], 'version': 1}],
            rid,
        )
        db.execute('INSERT INTO accord_decision_handoffs VALUES(?,?,?)', (rid, body.target_id, tid))
        return {'id': tid}

    return operate(uid, body, 'topic:handoff:' + rid, run)
