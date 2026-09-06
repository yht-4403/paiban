import json
import os
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import test_collaboration as fixtures
import test_workflows as workflows

from accord_api.modules.agent_runs import service as runtime
from accord_api.modules.collaboration.repository import message
from accord_api.modules.coordination import generation, service
from accord_api.modules.knowledge import person_context
from accord_api.modules.knowledge.resources import create_resource
from accord_api.platform.ai.errors import ModelError
from accord_api.platform.db import database as store
from accord_api.platform.errors import DomainError


class CoordinationTests(unittest.TestCase):
    post = workflows.WorkflowTests.post
    get = workflows.WorkflowTests.get

    @classmethod
    def setUpClass(cls):
        if not hasattr(fixtures.CollaborationTests, 'ids'):
            fixtures.CollaborationTests.setUpClass()
        cls.clients, cls.ids = fixtures.CollaborationTests.clients, fixtures.CollaborationTests.ids
        with store.lock, store.connection() as db:
            for who in ('su', 'zhou'):
                create_resource(
                    db, cls.ids[who], '已共享的项目经验', '有可查证的协作经历。', 'team'
                )

    def setUp(self):
        self.addCleanup(
            lambda: store.execute(
                "UPDATE accord_flows SET status='error' WHERE status IN ('queued','running','summarizing')"
            )
        )

    def start(self, kind='sync', members=None, source_ids=None, task_type='normal'):
        return self.post(
            'lin',
            '/flows',
            {
                'kind': kind,
                'task_type': task_type,
                'title': '讨论交付 ' + uuid4().hex[:5],
                'body': '需要真实证据',
                'member_ids': members or [self.ids['su'], self.ids['zhou']],
                'source_ids': source_ids or [],
            },
        )['id']

    def run_flow(self, fid, outcome=None):
        outcome = outcome or {
            'summary': '这是根据本轮证据形成的摘要。',
            'candidates': [],
            'actions': [],
        }

        def model(messages, cancelled, effort, tool=None, on_usage=None, **kwargs):
            if tool:
                result = tool.execute(uuid4().hex, 'person_context', {'query': '经验和待办'})
                return '已实际读取 ' + str(len(result['sources'])) + ' 项获准上下文。'
            return json.dumps(outcome, ensure_ascii=False)

        with patch.object(generation, 'model', side_effect=model):
            generation.execute(fid)
        return self.get('lin', '/flows/' + fid)

    def share(self, who, kind, sid, enabled=True):
        return self.post(
            who, '/context-sharing', {'source_kind': kind, 'source_id': sid, 'enabled': enabled}
        )

    def test_four_sources_are_owned_scoped_and_revocable(self):
        owner = self.ids['su']
        audience = [self.ids['lin'], owner]
        tid = self.post('su', '/threads', {'target_id': owner, 'title': 'WORK-CONTEXT'})['id']
        with store.lock, store.connection() as db:
            message(db, tid, 'human', owner, 'WORK-ONLY-WHEN-SHARED')
            shared = create_resource(db, owner, '公开经历', 'EXPERIENCE', 'team')
            private = create_resource(db, owner, '私人资料', 'NEVER-LEAK', 'private')
            memory = create_resource(
                db, owner, '已沉淀记忆', 'MEMORY-EVIDENCE', 'team', kind='memory'
            )
        before = person_context.collect(store.connection(), owner, audience)
        raw = json.dumps(before)
        self.assertIn(shared, raw)
        self.assertIn(memory, raw)
        self.assertNotIn(private, raw)
        self.assertNotIn('WORK-ONLY-WHEN-SHARED', raw)
        self.share('su', 'conversation', tid)
        self.share('su', 'state', owner)
        result = person_context.collect(store.connection(), owner, audience)
        self.assertEqual(
            {r['source_kind'] for r in result['sources']},
            {'conversation', 'document', 'memory', 'state'},
        )
        self.assertIn('WORK-ONLY-WHEN-SHARED', json.dumps(result))
        self.share('su', 'conversation', tid, False)
        with self.assertRaises(DomainError):
            person_context.validate(store.connection(), result['sources'], audience)
        self.post(
            'lin',
            '/context-sharing',
            {'source_kind': 'conversation', 'source_id': tid, 'enabled': True},
            status=404,
        )
        self.share('su', 'state', owner, False)

    def test_sync_queries_agents_without_notifying_people_and_saves_private_memory(self):
        fid = self.start()
        self.get('su', '/flows/' + fid, 404)
        self.assertNotIn(fid, [f['id'] for f in self.get('su', '/state')['flows']])
        result = self.run_flow(fid)
        self.assertEqual(result['status'], 'closed')
        self.assertEqual(len(result['evidence']), 3)
        calls = store.query(
            "SELECT * FROM accord_flow_calls WHERE flow_id=? AND status='done'", (fid,)
        )
        self.assertEqual(len(calls), 4)
        memories = store.query('SELECT * FROM accord_flow_memories WHERE flow_id=?', (fid,))
        self.assertEqual(len(memories), 3)
        self.assertTrue(
            all(
                store.query_one(
                    'SELECT scope FROM accord_resources WHERE id=?', (m['resource_id'],)
                )['scope']
                == 'private'
                for m in memories
            )
        )
        generation.execute(fid)
        self.assertEqual(
            len(store.query('SELECT * FROM accord_flow_memories WHERE flow_id=?', (fid,))), 3
        )

    def test_explicit_sources_are_the_only_context_for_each_person(self):
        selected = {}
        old = {}
        conversations = {}
        for who in ('lin', 'su', 'zhou'):
            old[who] = self.post(
                who,
                '/resources',
                {
                    'title': '旧高相关资料 ' + who,
                    'body': '经验和待办：OLD-HIGH-RELEVANCE-' + who,
                    'scope': 'team',
                },
            )['id']
            selected[who] = self.post(
                who,
                '/resources',
                {
                    'title': '本轮指定资料 ' + who,
                    'body': 'ONLY-SELECTED-CONTEXT-' + who,
                    'scope': 'team',
                },
            )['id']
            conversations[who] = self.post(
                who, '/threads', {'target_id': self.ids[who], 'title': '旧会话 ' + who}
            )['id']
            self.share(who, 'conversation', conversations[who])
            self.share(who, 'state', self.ids[who])

        self.addCleanup(
            lambda: store.execute(
                'DELETE FROM accord_context_grants WHERE source_id IN (?,?,?,?,?,?)',
                (
                    *conversations.values(),
                    *self.ids.values(),
                ),
            )
        )
        with store.lock, store.connection() as db:
            for who in ('lin', 'su', 'zhou'):
                message(
                    db,
                    conversations[who],
                    'human',
                    self.ids[who],
                    'OLD-CONVERSATION-' + who,
                )
                create_resource(
                    db,
                    self.ids[who],
                    '旧记忆 ' + who,
                    'OLD-MEMORY-' + who,
                    'team',
                    kind='memory',
                )

        source_ids = list(selected.values())
        fid = self.start(source_ids=source_ids)
        self.assertEqual(
            json.loads(
                store.query_one('SELECT source_ids FROM accord_flows WHERE id=?', (fid,))[
                    'source_ids'
                ]
            ),
            source_ids,
        )
        result = self.run_flow(fid)

        self.assertNotIn('source_ids', result)
        listed = next(flow for flow in self.get('lin', '/state')['flows'] if flow['id'] == fid)
        self.assertNotIn('source_ids', listed)
        for item in result['evidence']:
            alias = next(alias for alias, uid in self.ids.items() if uid == item['person_id'])
            self.assertTrue(item['sources'])
            self.assertEqual({source['id'] for source in item['sources']}, {selected[alias]})
            self.assertEqual({source['source_kind'] for source in item['sources']}, {'document'})
        evidence_json = json.dumps(result['evidence'])
        self.assertTrue(
            set(old.values()).isdisjoint(
                {source['id'] for item in result['evidence'] for source in item['sources']}
            )
        )
        self.assertNotIn('conversation', evidence_json)
        self.assertNotIn('memory', evidence_json)
        self.assertNotIn('state', evidence_json)

        self.post(
            'su',
            f'/resources/{selected["su"]}/update',
            {
                'expected_version': 1,
                'title': '已收回的本轮指定资料',
                'body': 'ONLY-SELECTED-CONTEXT-su',
                'scope': 'private',
            },
        )
        changed = self.get('lin', '/flows/' + fid)
        self.assertTrue(changed['sources_changed'])
        self.assertEqual(changed['evidence'], [])
        self.assertEqual(changed['result'], {})

    def test_explicit_sources_require_visible_owned_material_for_every_member(self):
        selected = {
            who: self.post(
                who,
                '/resources',
                {'title': '限定来源 ' + who, 'body': 'SOURCE-' + who, 'scope': 'team'},
            )['id']
            for who in ('lin', 'su', 'zhou')
        }
        payload = {
            'kind': 'sync',
            'title': '限定来源校验',
            'body': '只读指定资料',
            'member_ids': [self.ids['su'], self.ids['zhou']],
        }
        self.post(
            'lin',
            '/flows',
            {**payload, 'source_ids': [selected['lin'], selected['su']]},
            status=422,
        )

        private = self.post(
            'lin',
            '/resources',
            {'title': '私人来源', 'body': 'PRIVATE', 'scope': 'private'},
        )['id']
        self.post(
            'lin',
            '/flows',
            {**payload, 'source_ids': [private, selected['su'], selected['zhou']]},
            status=422,
        )

        with store.lock, store.connection() as db:
            cross_roster = create_resource(
                db,
                'fixed_trial_1',
                '另一个账号组的资料',
                'CROSS-ROSTER',
                'team',
            )
        self.post(
            'lin',
            '/flows',
            {**payload, 'source_ids': [selected['lin'], selected['su'], cross_roster]},
            status=422,
        )
        self.post(
            'lin',
            '/flows',
            {**payload, 'source_ids': [selected['lin'], selected['su'], 'missing-resource']},
            status=422,
        )

    def test_coordination_migration_preserves_old_flows_and_adds_exploration_schema(self):
        code = r'''
import json
import os
import sqlite3
import tempfile

with tempfile.TemporaryDirectory() as directory:
    os.environ['ACCORD_DATA_DIR'] = directory
    from accord_api.platform.db import database as store
    from accord_api.platform.db.migrations import coordination

    db = store.connection()
    db.executescript("""
    CREATE TABLE accord_task_acl(
      task_id TEXT PRIMARY KEY, creator_id TEXT NOT NULL, thread_id TEXT NOT NULL);
    CREATE TABLE accord_flows(
      id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, kind TEXT NOT NULL,
      title TEXT NOT NULL, body TEXT NOT NULL, member_ids TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'queued', result TEXT NOT NULL DEFAULT '{}',
      evidence TEXT NOT NULL DEFAULT '[]', error TEXT NOT NULL DEFAULT '',
      thread_id TEXT NOT NULL DEFAULT '', task_id TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    INSERT INTO accord_flows(id,owner_id,kind,title,body,member_ids,created_at,updated_at)
      VALUES('flow_old','owner','sync','old','body','["owner"]','before','before');
    """)
    coordination.initialize()
    row = db.execute(
        "SELECT id,title,source_ids,task_type,topic_id FROM accord_flows WHERE id='flow_old'"
    ).fetchone()
    assert dict(row) == {
        'id': 'flow_old', 'title': 'old', 'source_ids': '[]',
        'task_type': 'normal', 'topic_id': ''
    }, dict(row)
    assert db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='accord_task_topics'"
    ).fetchone()
    assert db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='accord_round_directions'"
    ).fetchone()
'''
        env = dict(os.environ, PYTHONPATH=str(os.path.dirname(os.path.dirname(__file__))))
        completed = subprocess.run(
            [sys.executable, '-c', code], env=env, capture_output=True, text=True
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_old_normal_start_operation_replays_after_type_upgrade(self):
        import hashlib

        operation_id = str(uuid4())
        payload = {
            'operation_id': operation_id,
            'kind': 'assignment',
            'title': '跨版本重放',
            'body': '升级前未包含任务类型。',
            'member_ids': [self.ids['su']],
            'source_ids': [],
        }
        fingerprint = hashlib.sha256(
            ('flow:start' + json.dumps(payload, sort_keys=True)).encode()
        ).hexdigest()
        store.execute(
            'INSERT INTO accord_operations(actor,operation_id,fingerprint,status,result) '
            'VALUES(?,?,?,?,?)',
            (self.ids['lin'], operation_id, fingerprint, 'done', '{"id":"flow_legacy"}'),
        )
        self.addCleanup(
            lambda: store.execute(
                'DELETE FROM accord_operations WHERE actor=? AND operation_id=?',
                (self.ids['lin'], operation_id),
            )
        )
        replayed = self.post(
            'lin',
            '/flows',
            {
                'kind': payload['kind'],
                'title': payload['title'],
                'body': payload['body'],
                'member_ids': payload['member_ids'],
            },
            operation=operation_id,
        )
        self.assertEqual(replayed, {'id': 'flow_legacy'})

    def test_assignment_type_defaults_validates_and_exploration_uses_topic_lifecycle(self):
        normal = self.post(
            'lin',
            '/flows',
            {
                'kind': 'assignment',
                'title': '旧请求默认普通任务',
                'body': '请推荐一位负责人',
                'member_ids': [self.ids['su']],
            },
        )['id']
        self.assertEqual(self.get('lin', '/flows/' + normal)['task_type'], 'normal')
        self.post(
            'lin',
            '/flows',
            {
                'kind': 'sync',
                'task_type': 'exploration',
                'title': '不支持的类型',
                'body': '只有任务分配可用',
                'member_ids': [self.ids['su']],
            },
            status=422,
        )
        self.post(
            'lin',
            '/flows',
            {
                'kind': 'assignment',
                'task_type': 'unknown',
                'title': '错误类型',
                'body': '不应创建',
                'member_ids': [self.ids['su']],
            },
            status=422,
        )
        store.execute("UPDATE accord_flows SET status='error' WHERE id=?", (normal,))

        fid = self.start(
            'assignment', members=[self.ids['su'], self.ids['zhou']], task_type='exploration'
        )
        self.run_flow(
            fid,
            {
                'summary': '建议由两位成员独立探索。',
                'candidates': [
                    {'person_id': self.ids['su'], 'reason': '适合方向一'},
                    {'person_id': self.ids['zhou'], 'reason': '适合方向二'},
                ],
                'actions': [],
            },
        )
        operation = str(uuid4())
        assigned = self.post(
            'lin',
            f'/flows/{fid}/choose',
            {'member_ids': [self.ids['su']]},
            operation=operation,
        )
        self.assertEqual(
            assigned,
            self.post(
                'lin',
                f'/flows/{fid}/choose',
                {'member_ids': [self.ids['su']]},
                operation=operation,
            ),
        )
        self.assertEqual(assigned['task_type'], 'exploration')
        self.assertTrue(assigned['topic_id'])
        self.assertEqual(len(assigned['task_ids']), 2)
        self.get('zhou', '/topics/' + assigned['topic_id'], status=404)
        self.get('zhou', '/flows/' + fid, status=404)

        own_tasks = {}
        for who in ('lin', 'su'):
            state = self.get(who, '/state')
            topic = next(item for item in state['topics'] if item['id'] == assigned['topic_id'])
            self.assertEqual(topic['task_type'], 'exploration')
            self.assertEqual(topic['completion_state'], 'in_progress')
            task = next(
                item
                for item in state['tasks']
                if item['topic_id'] == assigned['topic_id'] and item['assignee_id'] == self.ids[who]
            )
            own_tasks[who] = task
            self.assertEqual(task['task_type'], 'exploration')
            self.assertEqual(task['exploration']['attention'], 'in_progress')
            detail = self.get(who, f'/tasks/{task["id"]}/exploration')
            self.assertEqual(detail['topic']['id'], assigned['topic_id'])

        task_id = own_tasks['su']['id']
        self.post('su', f'/tasks/{task_id}/tick', status=409)
        self.post('su', f'/tasks/{task_id}/status', {'status': 'done'}, status=409)
        self.post('su', f'/tasks/{task_id}/delete', status=409)

        for who, label in (('lin', '轻量分岔'), ('su', '陪伴式探索')):
            self.post(
                who,
                f'/topics/{assigned["topic_id"]}/direction',
                {'expected_version': 0, 'label': label},
            )
        exploring = self.get('su', '/topics/' + assigned['topic_id'])
        self.assertEqual(
            {item['label'] for item in exploring['directions']}, {'轻量分岔', '陪伴式探索'}
        )
        self.assertEqual(exploring['proposals'], [])
        self.assertEqual(exploring['public_direction_count'], 2)

        self.post(
            'lin',
            f'/topics/{assigned["topic_id"]}/submit',
            {
                'expected_version': 0,
                'title': '轻量分岔',
                'body': '假设、流程、发现、风险和下一步。',
            },
        )
        current = self.get('lin', '/topics/' + assigned['topic_id'])
        self.post(
            'lin',
            f'/topics/{assigned["topic_id"]}/release',
            {'expected_version': current['version']},
            status=409,
        )
        self.post(
            'su',
            f'/topics/{assigned["topic_id"]}/submit',
            {
                'expected_version': 0,
                'title': '陪伴式探索',
                'body': '独立的假设、流程、发现、风险和下一步。',
            },
        )
        ready = self.get('lin', '/topics/' + assigned['topic_id'])
        self.assertTrue(ready['all_submitted'])
        self.assertTrue(ready['is_highlighted'])
        self.assertEqual(ready['attention'], 'ready_to_release')
        self.assertEqual(ready['completion_state'], 'ready_for_review')
        self.assertTrue(
            next(
                task
                for task in self.get('su', '/state')['tasks']
                if task['id'] == own_tasks['su']['id']
            )['status']
            == 'done'
        )

        self.post(
            'lin',
            f'/topics/{assigned["topic_id"]}/release',
            {'expected_version': ready['version']},
        )
        reviewing = self.get('lin', '/topics/' + assigned['topic_id'])
        self.assertEqual(reviewing['stage'], 'reviewing')
        self.assertEqual(reviewing['direction_count'], 2)
        self.assertEqual(reviewing['attention'], 'needs_decision')
        self.assertEqual(len(reviewing['proposals']), 2)
        self.post(
            'lin',
            f'/topics/{assigned["topic_id"]}/decision',
            {
                'expected_version': reviewing['version'],
                'body': '选择轻量分岔，保留陪伴式探索的分歧；下一步用真实任务验证。',
                'proposal_ids': [reviewing['proposals'][0]['proposal_id']],
            },
        )
        decided = self.get('su', f'/tasks/{own_tasks["su"]["id"]}/exploration')
        self.assertEqual(decided['topic']['stage'], 'decided')
        self.assertEqual(decided['task']['exploration']['attention'], 'results_available')
        self.assertTrue(decided['task']['exploration']['results_available'])
        self.assertIn('下一步', decided['topic']['decision']['body'])

    def test_assignment_requires_selection_and_does_not_impersonate_acceptance(self):
        fid = self.start('assignment')
        result = self.run_flow(
            fid,
            {
                'summary': '乙有相关经验。',
                'candidates': [{'person_id': self.ids['su'], 'reason': '已共享的经历与任务匹配'}],
                'actions': [],
            },
        )
        self.assertEqual(result['status'], 'ready')
        self.assertFalse(result['task_id'])
        self.post('su', f'/flows/{fid}/choose', {'member_ids': [self.ids['su']]}, status=404)
        self.post('lin', f'/flows/{fid}/choose', {'member_ids': [self.ids['zhou']]}, status=422)
        op = str(uuid4())
        created = self.post(
            'lin', f'/flows/{fid}/choose', {'member_ids': [self.ids['su']]}, operation=op
        )
        again = self.post(
            'lin', f'/flows/{fid}/choose', {'member_ids': [self.ids['su']]}, operation=op
        )
        self.assertEqual(created, again)
        task = next(t for t in self.get('su', '/state')['tasks'] if t['id'] == created['task_id'])
        self.assertEqual(task['assign_reason'], '任务分配')
        self.assertEqual(
            self.get('su', '/threads/' + task['thread_id'])['thread']['status'], 'closed'
        )
        self.post(
            'su',
            '/threads/' + task['thread_id'] + '/messages',
            {'body': '不能绕过 Agent 开真人通道'},
            status=409,
        )
        self.post('lin', f'/tasks/{task["id"]}/status', {'status': 'done'}, status=404)
        self.post('su', f'/tasks/{task["id"]}/status', {'status': 'done'})
        self.get('zhou', '/flows/' + fid, 404)

    def test_assignment_without_candidate_retries_in_the_same_explicit_scope(self):
        selected = {
            who: self.post(
                who,
                '/resources',
                {
                    'title': '重试限定来源 ' + who,
                    'body': 'RETRY-SELECTED-' + who,
                    'scope': 'team',
                },
            )['id']
            for who in ('lin', 'su', 'zhou')
        }
        source_ids = list(selected.values())
        fid = self.start('assignment', source_ids=source_ids)
        first = self.run_flow(
            fid,
            {'summary': '本轮证据暂未产生候选人。', 'candidates': [], 'actions': []},
        )
        self.assertEqual(first['status'], 'ready')
        self.assertEqual(first['result']['candidates'], [])

        self.post('lin', f'/flows/{fid}/retry')
        self.assertEqual(self.get('lin', '/flows/' + fid)['status'], 'queued')
        stored = store.query_one('SELECT source_ids FROM accord_flows WHERE id=?', (fid,))
        self.assertEqual(json.loads(stored['source_ids']), source_ids)

        second = self.run_flow(
            fid,
            {
                'summary': '测试乙的指定资料与任务匹配。',
                'candidates': [{'person_id': self.ids['su'], 'reason': '指定资料提供了依据'}],
                'actions': [],
            },
        )
        self.assertEqual(second['status'], 'ready')
        for item in second['evidence']:
            alias = next(alias for alias, uid in self.ids.items() if uid == item['person_id'])
            self.assertEqual({source['id'] for source in item['sources']}, {selected[alias]})

        assigned = self.post('lin', f'/flows/{fid}/choose', {'member_ids': [self.ids['su']]})
        summary = self.post('su', f'/tasks/{assigned["task_id"]}/tick', {})
        assignment_scope = store.query_one(
            'SELECT source_ids FROM accord_flows WHERE id=?', (fid,)
        )['source_ids']
        summary_scope = store.query_one(
            'SELECT source_ids FROM accord_flows WHERE id=?', (summary['id'],)
        )['source_ids']
        self.assertEqual(json.loads(assignment_scope), source_ids)
        self.assertEqual(json.loads(summary_scope), [])

    def test_decision_meeting_owner_publishes_tasks_and_completion_unlocks_follow_up(self):
        fid = self.start('decision')
        self.run_flow(
            fid,
            {
                'summary': '需讨论验收。',
                'candidates': [{'person_id': self.ids['su'], 'reason': '关键决策人'}],
                'actions': [],
            },
        )
        tid = self.post('lin', f'/flows/{fid}/choose', {'member_ids': [self.ids['su']]})[
            'thread_id'
        ]
        self.get('zhou', '/flows/' + fid, 404)
        self.post('su', f'/groups/{tid}/messages', {'body': '我来完成验收。'})
        self.post('su', f'/flows/{fid}/finish', status=403)
        self.post('lin', f'/flows/{fid}/finish')
        self.post('su', f'/groups/{tid}/messages', {'body': '会后不能继续写入'}, status=409)
        result = self.run_flow(
            fid,
            {
                'summary': '乙表示负责验收。',
                'candidates': [],
                'actions': [
                    {
                        'person_id': self.ids['su'],
                        'title': '完成验收',
                        'detail': '执行本轮讨论的验收',
                    },
                    {'person_id': self.ids['lin'], 'title': '同步验收结论', 'detail': '发送结论'},
                ],
            },
        )
        self.assertEqual(result['status'], 'closed')
        action = next(a for a in result['actions'] if a['assignee_id'] == self.ids['su'])
        assigned = self.post('lin', f'/flow-actions/{action["id"]}/accept')['task_id']
        self.assertEqual(
            self.post('su', f'/flow-actions/{action["id"]}/accept')['task_id'], assigned
        )
        self.assertIn(assigned, [t['id'] for t in self.get('su', '/state')['tasks']])
        self.assertNotIn(assigned, [t['id'] for t in self.get('zhou', '/state')['tasks']])
        another = next(a for a in result['actions'] if a['assignee_id'] == self.ids['lin'])
        second = self.post('lin', f'/flow-actions/{another["id"]}/accept')['task_id']
        self.assertNotEqual(assigned, second)
        self.assertEqual(
            len(store.query('SELECT * FROM accord_task_acl WHERE thread_id=?', (tid,))), 2
        )
        before = self.get('lin', '/flows/' + fid)['follow_up']
        self.assertEqual(before['completed_count'], 0)
        self.assertFalse(before['ready'])
        self.post('su', f'/flows/{fid}/follow-up', {'action': 'create'}, status=403)
        store.execute(
            "UPDATE tasks SET status='done',artifact='已完成真实验收并上传结果' WHERE id IN (?,?)",
            (assigned, second),
        )
        ready = self.get('lin', '/flows/' + fid)
        self.assertTrue(ready['follow_up']['ready'])
        self.assertEqual(ready['follow_up']['status'], 'suggested')
        self.assertIn(
            '已完成真实验收',
            next(a for a in ready['actions'] if a['task_id'] == assigned)['task_artifact'],
        )
        self.assertTrue(
            next(f for f in self.get('lin', '/state')['flows'] if f['id'] == fid)['follow_up_ready']
        )
        operation = str(uuid4())
        continued = self.post(
            'lin',
            f'/flows/{fid}/follow-up',
            {'action': 'create', 'kind': 'sync'},
            operation=operation,
        )
        self.assertEqual(
            self.post(
                'lin',
                f'/flows/{fid}/follow-up',
                {'action': 'create', 'kind': 'sync'},
                operation=operation,
            )['id'],
            continued['id'],
        )
        next_flow = self.get('lin', '/flows/' + continued['id'])
        self.assertEqual(next_flow['kind'], 'sync')
        self.assertEqual(next_flow['status'], 'queued')
        self.assertFalse(
            next(f for f in self.get('lin', '/state')['flows'] if f['id'] == fid)['follow_up_ready']
        )

    def peer(self):
        tid = self.post('lin', '/threads', {'target_id': self.ids['su']})['id']
        rid = self.post('lin', f'/threads/{tid}/messages', {'body': '需要核对下一步'})['run_id']
        with patch(
            'accord_api.modules.agent_runs.service.agent.stream_answer', side_effect=fixtures.reply
        ):
            runtime.execute_run(rid)
        self.post('lin', f'/threads/{tid}/handoff', {'mode': 'now'})
        self.post('su', f'/threads/{tid}/messages', {'body': '先核对结果，暂无后续任务。'})
        return tid

    def test_chat_close_is_same_thread_idempotent_and_optional_todos(self):
        tid = self.peer()
        fid = self.post('su', f'/threads/{tid}/close')['id']
        self.assertEqual(self.post('lin', f'/threads/{tid}/close')['id'], fid)
        self.assertEqual(self.get('su', '/threads/' + tid)['thread']['status'], 'closed')
        self.post('lin', f'/threads/{tid}/messages', {'body': '不应写进已结束会话'}, status=409)
        self.run_flow(fid)
        result = self.get('su', '/flows/' + fid)
        self.assertEqual(result['actions'], [])
        self.assertEqual(result['status'], 'closed')
        self.get('zhou', '/flows/' + fid, 404)

    def test_idle_close_uses_last_message_not_countdown_popup(self):
        tid = self.peer()
        store.execute(
            'UPDATE accord_threads SET updated_at=? WHERE id=?',
            ((datetime.now(timezone.utc) - timedelta(minutes=31)).isoformat(), tid),
        )
        service.close_idle()
        service.close_idle()
        self.assertEqual(
            len(
                store.query(
                    "SELECT id FROM accord_flows WHERE kind='chat_summary' AND thread_id=?", (tid,)
                )
            ),
            1,
        )

    def test_model_failure_does_not_save_success_and_can_retry(self):
        fid = self.start()
        with patch.object(generation, 'model', side_effect=ModelError('upstream', '模型不可用')):
            generation.execute(fid)
        result = self.get('lin', '/flows/' + fid)
        self.assertEqual(result['status'], 'error')
        self.assertIn('模型不可用', result['error'])
        self.assertFalse(store.query('SELECT * FROM accord_flow_memories WHERE flow_id=?', (fid,)))
        self.post('lin', f'/flows/{fid}/retry')
        self.assertEqual(self.run_flow(fid)['status'], 'closed')

    def test_revoked_evidence_blocks_assignment(self):
        rid = self.post(
            'su',
            '/resources',
            {'title': '经验：撤权测试', 'body': 'MATCHING-WORK', 'scope': 'team'},
        )['id']
        fid = self.start('assignment')
        result = self.run_flow(
            fid,
            {
                'summary': '依据公开资料。',
                'candidates': [{'person_id': self.ids['su'], 'reason': '有经历'}],
                'actions': [],
            },
        )
        self.assertTrue(
            any(ref['id'] == rid for item in result['evidence'] for ref in item['sources'])
        )
        self.post(
            'su',
            f'/resources/{rid}/update',
            {
                'expected_version': 1,
                'title': '经验：撤权测试',
                'body': 'MATCHING-WORK',
                'scope': 'private',
            },
        )
        data = self.get('lin', '/flows/' + fid)
        self.assertTrue(data['sources_changed'])
        self.assertEqual(data['result'], {})
        self.post('lin', f'/flows/{fid}/choose', {'member_ids': [self.ids['su']]}, status=404)

    def test_group_people_can_send_while_agent_runs(self):
        tid = self.post('lin', '/groups', {'member_ids': [self.ids['su'], self.ids['zhou']]})['id']
        run = self.post(
            'lin', f'/groups/{tid}/messages', {'body': '请检查', 'agent_id': self.ids['su']}
        )['run_id']
        self.post('zhou', f'/groups/{tid}/messages', {'body': '人可以继续补充。'})
        self.post(
            'lin',
            f'/groups/{tid}/messages',
            {'body': '不能重复触发', 'agent_id': self.ids['su']},
            status=409,
        )
        self.post('lin', f'/runs/{run}/stop')
