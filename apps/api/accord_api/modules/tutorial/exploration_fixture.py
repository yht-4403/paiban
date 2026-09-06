"""A clearly labelled, read-only exploration example for the three trial identities."""

import json

from accord_api.modules.identity import service as identity
from accord_api.modules.knowledge import index
from accord_api.modules.knowledge.resources import create_resource
from accord_api.platform.commands import operate
from accord_api.platform.db import database as store
from accord_api.platform.errors import DomainError

ROUND_ID = 'tutorial_exploration_round_v1'
BRIEF_ID = 'tutorial_exploration_brief_v1'
DECISION_ID = 'tutorial_exploration_decision_v1'
MEMBER_IDS = ('fixed_trial_1', 'fixed_trial_2', 'fixed_trial_3')
TASK_IDS = {member: f'tutorial_exploration_task_{member}_v1' for member in MEMBER_IDS}
THREAD_IDS = {member: f'tutorial_exploration_thread_{member}_v1' for member in MEMBER_IDS}

PROPOSALS = (
    {
        'member_id': 'fixed_trial_1',
        'proposal_id': 'tutorial_exploration_proposal_1_v1',
        'resource_id': 'tutorial_exploration_release_1_v1',
        'direction': '即时分岔：把下一步压缩成一次轻量选择',
        'body': """## 核心假设

当用户只需选择一个足够小的下一步时，更容易从讨论进入行动。

## 使用流程

识别卡点 → 给出三个轻量下一步 → 用户任选一个 → 记录反馈。

## 当前发现

入口清楚、操作成本低，适合作为第一次体验。

## 主要风险

过度压缩可能掩盖复杂问题，仍需允许用户展开依据。

## 下一步验证

用 5 次真实任务分配记录选择率与撤回原因。""",
    },
    {
        'member_id': 'fixed_trial_2',
        'proposal_id': 'tutorial_exploration_proposal_2_v1',
        'resource_id': 'tutorial_exploration_release_2_v1',
        'direction': '陪伴式探索：让 Agent 用追问帮助形成方向',
        'body': """## 核心假设

模糊课题需要先澄清动机和约束，再进入方案比较。

## 使用流程

描述困惑 → Agent 追问关键约束 → 生成方向草案 → 用户封存公开版本。

## 当前发现

适合尚未形成明确问题的团队，但耗时高于即时分岔。

## 主要风险

追问过多会让用户觉得流程拖沓，Agent 也不能替人决定方向。

## 下一步验证

比较 3 问与 6 问版本的完成率和主观负担。""",
    },
    {
        'member_id': 'fixed_trial_3',
        'proposal_id': 'tutorial_exploration_proposal_3_v1',
        'resource_id': 'tutorial_exploration_release_3_v1',
        'direction': '场景触发：在工作流卡住时主动呈现探索入口',
        'body': """## 核心假设

把探索入口放在已有待办旁，比要求用户另开工具更容易被采用。

## 使用流程

待办停滞 → 展示探索提示 → 独立产出方向 → 回到原待办集中比较。

## 当前发现

与现有工作台衔接自然，能保留任务上下文。

## 主要风险

触发过于频繁会形成打扰，且不能根据沉默猜测成员没有进展。

## 下一步验证

仅在用户主动选择“创新探索”时触发，并记录关闭原因。""",
    },
)

DECISION_BODY = """## 本轮选择

先推进“场景触发”，同时保留“即时分岔”作为卡片内的快捷动作。

## 选择理由与保留分歧

它最容易嵌入现有任务分配和待办路径；陪伴式探索对模糊问题更完整，但交互成本仍需验证。三条方向均保留，不把未验证假设写成团队事实。

## 下一步

由体验者一组织 5 次虚拟走查，体验者二记录理解偏差，体验者三复核高亮卡片在 1440 / 768 / 390 宽度下的可读性。

> 这是预置的虚拟实例，仅用于展示信息结构；不代表模型运行、真实任务完成或用户研究结论。"""


def _reserved_resource_ids():
    return [BRIEF_ID, DECISION_ID, *(item['resource_id'] for item in PROPOSALS)]


def _assert_trial(uid):
    if uid not in MEMBER_IDS or identity.account_roster(uid) != 'trial':
        raise DomainError(403, '仅体验账号可以准备创新探索虚拟实例。')


def _summary(created):
    return {
        'id': ROUND_ID,
        'topic_id': ROUND_ID,
        'task_ids': list(TASK_IDS.values()),
        'member_ids': list(MEMBER_IDS),
        'origin': 'tutorial_fixture',
        'is_fixture': True,
        'created': created,
        'resettable': True,
    }


def _resource_matches(db, resource_id, owner_id, kind, title, body, refs=None):
    row = db.execute(
        """SELECT r.owner_id,r.kind,r.scope,r.round_id,r.version,r.active,
        v.title,v.body,v.refs FROM accord_resources r
        JOIN accord_resource_versions v ON v.resource_id=r.id AND v.version=r.version
        WHERE r.id=?""",
        (resource_id,),
    ).fetchone()
    try:
        saved_refs = json.loads(row['refs']) if row else None
    except (TypeError, json.JSONDecodeError):
        return False
    return bool(
        row
        and row['owner_id'] == owner_id
        and row['kind'] == kind
        and row['scope'] == 'round'
        and row['round_id'] == ROUND_ID
        and row['version'] == 1
        and row['active'] == 1
        and row['title'] == title
        and row['body'] == body
        and saved_refs == (refs or [])
    )


def _assert_existing(db):
    row = db.execute('SELECT * FROM accord_rounds WHERE id=?', (ROUND_ID,)).fetchone()
    if not row:
        return False
    linked = db.execute(
        'SELECT task_id,member_id,origin FROM accord_task_topics WHERE round_id=? ORDER BY member_id',
        (ROUND_ID,),
    ).fetchall()
    proposal_ids = {
        row['id']
        for row in db.execute('SELECT id FROM accord_proposals WHERE round_id=?', (ROUND_ID,))
    }
    task_shapes = {
        (item['id'], item['assignee_id'], item['creator_id'], item['thread_id'], item['status'])
        for item in db.execute(
            """SELECT t.id,t.assignee_id,t.status,a.creator_id,a.thread_id
            FROM tasks t JOIN accord_task_acl a ON a.task_id=t.id
            JOIN accord_task_topics l ON l.task_id=t.id WHERE l.round_id=?""",
            (ROUND_ID,),
        )
    }
    thread_shapes = {
        (item['id'], item['owner_id'], item['target_id'], item['kind'], item['status'])
        for item in db.execute(
            """SELECT t.id,t.owner_id,t.target_id,t.kind,t.status
            FROM accord_threads t JOIN accord_thread_scopes s ON s.thread_id=t.id
            WHERE s.round_id=? AND s.purpose='exploration'""",
            (ROUND_ID,),
        )
    }
    proposal_shapes = {
        (
            item['id'],
            item['author_id'],
            item['version'],
            item['title'],
            item['body'],
            item['sources'],
        )
        for item in db.execute('SELECT * FROM accord_proposals WHERE round_id=?', (ROUND_ID,))
    }
    submission_shapes = {
        (item['member_id'], item['proposal_id'], item['version'])
        for item in db.execute('SELECT * FROM accord_submissions WHERE round_id=?', (ROUND_ID,))
    }
    release_shapes = {
        (item['proposal_id'], item['resource_id'])
        for item in db.execute('SELECT * FROM accord_releases WHERE round_id=?', (ROUND_ID,))
    }
    direction_shapes = {
        (item['member_id'], item['label'], item['version'])
        for item in db.execute(
            'SELECT * FROM accord_round_directions WHERE round_id=?', (ROUND_ID,)
        )
    }
    expected_tasks = {
        (TASK_IDS[member], member, MEMBER_IDS[0], THREAD_IDS[member], 'done')
        for member in MEMBER_IDS
    }
    expected_threads = {
        (THREAD_IDS[member], member, member, 'workspace', 'closed') for member in MEMBER_IDS
    }
    expected_proposals = {
        (
            item['proposal_id'],
            item['member_id'],
            1,
            item['direction'],
            item['body'],
            '[]',
        )
        for item in PROPOSALS
    }
    expected_submissions = {(item['member_id'], item['proposal_id'], 1) for item in PROPOSALS}
    expected_releases = {(item['proposal_id'], item['resource_id']) for item in PROPOSALS}
    expected_directions = {(item['member_id'], item['direction'], 1) for item in PROPOSALS}
    expected_refs = [{'id': item['resource_id'], 'version': 1} for item in PROPOSALS]
    valid = (
        row['owner_id'] == MEMBER_IDS[0]
        and row['brief_id'] == BRIEF_ID
        and row['decision_id'] == DECISION_ID
        and row['stage'] == 'decided'
        and set(MEMBER_IDS)
        == {
            item['member_id']
            for item in db.execute(
                'SELECT member_id FROM accord_round_members WHERE round_id=?', (ROUND_ID,)
            )
        }
        and {(item['member_id'], item['task_id'], item['origin']) for item in linked}
        == {(member, TASK_IDS[member], 'tutorial_fixture') for member in MEMBER_IDS}
        and proposal_ids == {item['proposal_id'] for item in PROPOSALS}
        and task_shapes == expected_tasks
        and thread_shapes == expected_threads
        and proposal_shapes == expected_proposals
        and submission_shapes == expected_submissions
        and release_shapes == expected_releases
        and direction_shapes == expected_directions
        and _resource_matches(
            db,
            BRIEF_ID,
            MEMBER_IDS[0],
            'brief',
            '【虚拟实例】更容易开始行动的产品机制 · 共同简报',
            '三位体验成员分别探索一种帮助用户开始行动的机制。私有过程不公开；封存后统一比较假设、流程、发现、风险和下一步。',
        )
        and all(
            _resource_matches(
                db,
                item['resource_id'],
                item['member_id'],
                'proposal',
                item['direction'],
                item['body'],
            )
            for item in PROPOSALS
        )
        and _resource_matches(
            db,
            DECISION_ID,
            MEMBER_IDS[0],
            'decision',
            '【虚拟实例】本轮决策与下一步',
            DECISION_BODY,
            expected_refs,
        )
    )
    if not valid:
        raise DomainError(409, '创新探索虚拟实例标识已被占用，未改写现有数据。')
    return True


def ensure(db):
    if _assert_existing(db):
        return _summary(False)
    reserved = []
    for table, ids in (
        ('tasks', TASK_IDS.values()),
        ('accord_threads', THREAD_IDS.values()),
        ('accord_proposals', (item['proposal_id'] for item in PROPOSALS)),
        ('accord_resources', _reserved_resource_ids()),
    ):
        reserved.extend(
            db.execute(f'SELECT 1 FROM {table} WHERE id=?', (reserved_id,)).fetchone()
            for reserved_id in ids
        )
    if any(reserved):
        raise DomainError(409, '创新探索虚拟实例标识已被占用，未改写现有数据。')

    now = store.now()
    create_resource(
        db,
        MEMBER_IDS[0],
        '【虚拟实例】更容易开始行动的产品机制 · 共同简报',
        '三位体验成员分别探索一种帮助用户开始行动的机制。私有过程不公开；封存后统一比较假设、流程、发现、风险和下一步。',
        scope='round',
        kind='brief',
        round_id=ROUND_ID,
        resource_id=BRIEF_ID,
    )
    db.execute(
        """INSERT INTO accord_rounds(
        id,title,owner_id,brief_id,stage,version,decision_id,created_at)
        VALUES(?,?,?,?,?,?,?,?)""",
        (
            ROUND_ID,
            '【虚拟实例】怎样让用户更容易开始行动？',
            MEMBER_IDS[0],
            BRIEF_ID,
            'decided',
            7,
            DECISION_ID,
            now,
        ),
    )
    db.executemany(
        'INSERT INTO accord_round_members(round_id,member_id) VALUES(?,?)',
        [(ROUND_ID, member) for member in MEMBER_IDS],
    )

    for member in MEMBER_IDS:
        thread_id = THREAD_IDS[member]
        task_id = TASK_IDS[member]
        db.execute(
            """INSERT INTO accord_threads(
            id,owner_id,target_id,title,kind,status,created_at,updated_at)
            VALUES(?,?,?,?,?,'closed',?,?)""",
            (
                thread_id,
                member,
                member,
                '【虚拟实例】行动机制 · 我的探索',
                'workspace',
                now,
                now,
            ),
        )
        db.execute(
            'INSERT INTO accord_thread_scopes(thread_id,purpose,round_id) VALUES(?,?,?)',
            (thread_id, 'exploration', ROUND_ID),
        )
        db.execute(
            """INSERT INTO tasks(
            id,title,detail,status,assignee_id,assign_reason,artifact,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                task_id,
                '【虚拟实例】探索一种更容易开始行动的机制',
                '从独立方向形成可比较的方案；这是预置演示数据，不代表真实执行。',
                'done',
                member,
                '创新探索 · 虚拟实例',
                '虚拟实例：示例方案已封存，不代表真实任务完成。',
                now,
                now,
            ),
        )
        db.execute(
            'INSERT INTO accord_task_acl(task_id,creator_id,thread_id) VALUES(?,?,?)',
            (task_id, MEMBER_IDS[0], thread_id),
        )
        db.execute(
            'INSERT INTO accord_task_topics(task_id,round_id,member_id,origin) VALUES(?,?,?,?)',
            (task_id, ROUND_ID, member, 'tutorial_fixture'),
        )

    for item in PROPOSALS:
        db.execute(
            """INSERT INTO accord_round_directions(round_id,member_id,label,version,updated_at)
            VALUES(?,?,?,?,?)""",
            (ROUND_ID, item['member_id'], item['direction'], 1, now),
        )
        db.execute(
            'INSERT INTO accord_proposals(id,round_id,author_id,version,title,body,sources,created_at) VALUES(?,?,?,?,?,?,?,?)',
            (
                item['proposal_id'],
                ROUND_ID,
                item['member_id'],
                1,
                item['direction'],
                item['body'],
                '[]',
                now,
            ),
        )
        db.execute(
            'INSERT INTO accord_submissions(round_id,member_id,proposal_id,version) VALUES(?,?,?,1)',
            (ROUND_ID, item['member_id'], item['proposal_id']),
        )
        create_resource(
            db,
            item['member_id'],
            item['direction'],
            item['body'],
            scope='round',
            kind='proposal',
            round_id=ROUND_ID,
            resource_id=item['resource_id'],
        )
        db.execute(
            'INSERT INTO accord_releases(round_id,proposal_id,resource_id,created_at) VALUES(?,?,?,?)',
            (ROUND_ID, item['proposal_id'], item['resource_id'], now),
        )

    create_resource(
        db,
        MEMBER_IDS[0],
        '【虚拟实例】本轮决策与下一步',
        DECISION_BODY,
        scope='round',
        kind='decision',
        round_id=ROUND_ID,
        refs=[{'id': item['resource_id'], 'version': 1} for item in PROPOSALS],
        resource_id=DECISION_ID,
    )
    return _summary(True)


def _remove(db):
    if not _assert_existing(db):
        return
    db.execute('DELETE FROM accord_round_directions WHERE round_id=?', (ROUND_ID,))
    db.execute('DELETE FROM accord_releases WHERE round_id=?', (ROUND_ID,))
    db.execute('DELETE FROM accord_submissions WHERE round_id=?', (ROUND_ID,))
    db.execute('DELETE FROM accord_proposals WHERE round_id=?', (ROUND_ID,))
    db.execute('DELETE FROM accord_decision_handoffs WHERE round_id=?', (ROUND_ID,))
    db.execute('DELETE FROM accord_task_topics WHERE round_id=?', (ROUND_ID,))
    for task_id in TASK_IDS.values():
        db.execute('DELETE FROM accord_task_priorities WHERE task_id=?', (task_id,))
        db.execute('DELETE FROM accord_task_acl WHERE task_id=?', (task_id,))
        db.execute('DELETE FROM tasks WHERE id=?', (task_id,))
    for thread_id in THREAD_IDS.values():
        db.execute('DELETE FROM accord_thread_archives WHERE thread_id=?', (thread_id,))
        db.execute('DELETE FROM accord_thread_scopes WHERE thread_id=?', (thread_id,))
        db.execute('DELETE FROM accord_placements WHERE thread_id=?', (thread_id,))
        db.execute('DELETE FROM accord_threads WHERE id=?', (thread_id,))
    db.execute('DELETE FROM accord_round_members WHERE round_id=?', (ROUND_ID,))
    db.execute('DELETE FROM accord_rounds WHERE id=?', (ROUND_ID,))
    for resource_id in _reserved_resource_ids():
        db.execute('DELETE FROM accord_resource_versions WHERE resource_id=?', (resource_id,))
        db.execute('DELETE FROM accord_resources WHERE id=?', (resource_id,))
        db.execute(
            'DELETE FROM accord_content_fts WHERE chunk_id IN '
            '(SELECT id FROM accord_content_chunks WHERE source_key=?)',
            ('resource:' + resource_id,),
        )
        db.execute(
            'DELETE FROM accord_content_chunks WHERE source_key=?', ('resource:' + resource_id,)
        )
        db.execute(
            "DELETE FROM accord_index_queue WHERE kind='resource' AND id=?",
            (resource_id,),
        )


def reset(uid, body):
    _assert_trial(uid)

    def run(db):
        _remove(db)
        result = ensure(db)
        while index.synchronize(db):
            pass
        return {**result, 'reset': True}

    return operate(uid, body, 'tutorial:exploration:reset', run)


def remove_for_test(db):
    """Remove only the reserved fixture; tests call this after checking ownership."""
    _remove(db)
