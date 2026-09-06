"""Guided trial preparation includes reference material and a labelled virtual instance."""

import os
import tempfile
import unittest
from uuid import uuid4

_temporary = None
if 'ACCORD_DATA_DIR' not in os.environ:
    _temporary = tempfile.TemporaryDirectory(prefix='accord-tutorial-test-')
    os.environ['ACCORD_DATA_DIR'] = _temporary.name

from fastapi.testclient import TestClient  # noqa: E402

from accord_api.app import app  # noqa: E402
from accord_api.modules.coordination import service as coordination_service  # noqa: E402
from accord_api.modules.identity import service as identity  # noqa: E402
from accord_api.modules.knowledge import index, resources, retrieval  # noqa: E402
from accord_api.modules.tutorial import exploration_fixture  # noqa: E402
from accord_api.modules.tutorial import service as tutorial  # noqa: E402
from accord_api.platform.db import database  # noqa: E402
from accord_api.platform.db.migrations import brand, fixed_member_names  # noqa: E402


class TutorialPreparationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self._remove_tutorial_resources()
        self.tokens = {
            account_id: self.client.post(
                '/api/auth/select', json={'account_id': account_id}
            ).json()['session_token']
            for account_id in (
                'fixed_demo_jiancheng',
                'fixed_trial_1',
                'fixed_trial_2',
                'fixed_trial_3',
            )
        }

    def tearDown(self):
        for token in self.tokens.values():
            identity.logout(token=token)
        self.client.close()
        self._remove_tutorial_resources()

    def _headers(self, account_id):
        return {'Authorization': f'Bearer {self.tokens[account_id]}'}

    def _remove_tutorial_resources(self):
        with database.lock, database.connection() as db:
            exploration_fixture.remove_for_test(db)
            for item in tutorial.TUTORIAL_RESOURCES:
                db.execute('DELETE FROM accord_resource_versions WHERE resource_id=?', (item.id,))
                db.execute('DELETE FROM accord_resources WHERE id=?', (item.id,))
            index.synchronize(db)
            for item in tutorial.TUTORIAL_RESOURCES:
                db.execute(
                    'DELETE FROM accord_content_chunks WHERE source_key=?',
                    ('resource:' + item.id,),
                )

    def _remove_resources(self, *resource_ids):
        with database.lock, database.connection() as db:
            for resource_id in resource_ids:
                db.execute(
                    'DELETE FROM accord_resource_versions WHERE resource_id=?', (resource_id,)
                )
                db.execute('DELETE FROM accord_resources WHERE id=?', (resource_id,))
            while index.synchronize(db):
                pass

    def _cancel_active_completion_flows(self, owner_id):
        with database.lock, database.connection() as db:
            db.execute(
                """UPDATE accord_flows SET status='cancelled'
                WHERE owner_id=? AND kind='task_summary' AND status!='closed'""",
                (owner_id,),
            )

    def _prepare(self, account_id='fixed_trial_1'):
        return self.client.post('/api/tutorial/prepare', headers=self._headers(account_id))

    def test_only_trial_accounts_can_prepare_and_demo_roster_cannot_read_samples(self):
        self.assertEqual(self.client.post('/api/tutorial/prepare').status_code, 401)
        self.assertEqual(self._prepare('fixed_demo_jiancheng').status_code, 403)

        prepared = self._prepare()
        self.assertEqual(prepared.status_code, 200)
        sample_ids = {item.id for item in tutorial.TUTORIAL_RESOURCES}

        trial_state = self.client.get('/api/state', headers=self._headers('fixed_trial_1')).json()
        demo_state = self.client.get(
            '/api/state', headers=self._headers('fixed_demo_jiancheng')
        ).json()
        self.assertTrue(sample_ids.issubset({item['id'] for item in trial_state['documents']}))
        self.assertTrue(sample_ids.isdisjoint({item['id'] for item in demo_state['documents']}))

        with database.lock:
            db = database.connection()
            trial_hits = retrieval.search(
                db,
                'fixed_trial_2',
                ['fixed_trial_1', 'fixed_trial_2'],
                '路演主线',
            )['sources']
            demo_hits = retrieval.search(db, 'fixed_trial_2', ['fixed_demo_jiancheng'], '路演主线')[
                'sources'
            ]
        self.assertIn('tutorial_context_fixed_trial_2_v1', {item['id'] for item in trial_hits})
        self.assertTrue(sample_ids.isdisjoint({item['id'] for item in demo_hits}))

        hidden = self.client.get(
            '/api/resources/tutorial_context_fixed_trial_2_v1',
            headers=self._headers('fixed_demo_jiancheng'),
        )
        self.assertEqual(hidden.status_code, 404)

    def test_prepare_is_idempotent_indexed_and_preserves_unrelated_trial_data(self):
        custom_id = 'resource_' + uuid4().hex[:12]
        custom_body = '这是体验者自己的原始资料，不应被教学准备流程改写。'
        with database.lock, database.connection() as db:
            resources.create_resource(
                db,
                'fixed_trial_1',
                '体验者自己的资料',
                custom_body,
                scope='team',
                resource_id=custom_id,
            )
            before = db.execute('SELECT count(*) FROM accord_resources').fetchone()[0]

        first = self._prepare('fixed_trial_2')
        second = self._prepare('fixed_trial_1')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()['created_count'], 3)
        self.assertTrue(all(item['created'] for item in first.json()['resources']))
        self.assertEqual(second.json()['created_count'], 0)
        self.assertTrue(all(not item['created'] for item in second.json()['resources']))

        with database.lock, database.connection() as db:
            self.assertEqual(
                db.execute('SELECT count(*) FROM accord_resources').fetchone()[0], before + 8
            )
            custom = db.execute(
                """SELECT r.owner_id,r.scope,v.title,v.body FROM accord_resources r
                JOIN accord_resource_versions v ON v.resource_id=r.id AND v.version=r.version
                WHERE r.id=?""",
                (custom_id,),
            ).fetchone()
            self.assertEqual(custom['owner_id'], 'fixed_trial_1')
            self.assertEqual(custom['scope'], 'team')
            self.assertEqual(custom['body'], custom_body)
            self.assertEqual(db.execute('SELECT count(*) FROM accord_index_queue').fetchone()[0], 0)
            for item in tutorial.TUTORIAL_RESOURCES:
                hits = retrieval.search(
                    db,
                    item.owner_id,
                    ['fixed_trial_1'],
                    item.focus.split('与')[0].split(' ')[0],
                )['sources']
                self.assertIn(item.id, {hit['id'] for hit in hits})

            db.execute('DELETE FROM accord_resource_versions WHERE resource_id=?', (custom_id,))
            db.execute('DELETE FROM accord_resources WHERE id=?', (custom_id,))
            index.synchronize(db)

    def test_prepare_creates_labelled_fixture_without_model_or_success_receipts(self):
        unchanged_tables = (
            'messages',
            'handoffs',
            'accord_runs',
            'accord_tool_calls',
            'accord_flows',
            'accord_flow_actions',
            'artifacts',
            'memories',
            'meeting_msgs',
        )
        with database.lock:
            db = database.connection()
            before = {
                table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                for table in unchanged_tables
            }
            created_before = {
                table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                for table in (
                    'accord_threads',
                    'tasks',
                    'accord_task_acl',
                    'accord_rounds',
                    'accord_round_members',
                    'accord_proposals',
                    'accord_submissions',
                    'accord_releases',
                    'accord_round_directions',
                )
            }

        prepared = self._prepare()
        self.assertEqual(prepared.status_code, 200)
        self.assertEqual(len(prepared.json()['resources']), 3)

        with database.lock:
            db = database.connection()
            after = {
                table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                for table in unchanged_tables
            }
            self.assertEqual(after, before)
            deltas = {
                table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] - count
                for table, count in created_before.items()
            }
            self.assertEqual(
                deltas,
                {
                    'accord_threads': 3,
                    'tasks': 3,
                    'accord_task_acl': 3,
                    'accord_rounds': 1,
                    'accord_round_members': 3,
                    'accord_proposals': 3,
                    'accord_submissions': 3,
                    'accord_releases': 3,
                    'accord_round_directions': 3,
                },
            )
            self.assertEqual(
                db.execute(
                    'SELECT count(*) FROM accord_task_topics WHERE origin=?',
                    ('tutorial_fixture',),
                ).fetchone()[0],
                3,
            )
            sample_rows = db.execute(
                """SELECT id,owner_id,kind,scope,version,active FROM accord_resources
                WHERE id LIKE 'tutorial_context_fixed_trial_%_v1' ORDER BY id"""
            ).fetchall()
            self.assertEqual(len(sample_rows), 3)
            self.assertTrue(
                all(
                    row['kind'] == 'note'
                    and row['scope'] == 'team'
                    and row['version'] == 1
                    and row['active'] == 1
                    for row in sample_rows
                )
            )

        fixture = prepared.json()['exploration_fixture']
        self.assertTrue(fixture['created'])
        self.assertTrue(fixture['is_fixture'])
        self.assertEqual(fixture['origin'], 'tutorial_fixture')

    def test_fixture_is_visible_to_all_three_trial_accounts_and_hidden_from_demo(self):
        prepared = self._prepare().json()
        fixture = prepared['exploration_fixture']
        self.assertEqual(fixture['member_ids'], list(exploration_fixture.MEMBER_IDS))

        tasks_by_account = {}
        for account_id in exploration_fixture.MEMBER_IDS:
            state = self.client.get('/api/state', headers=self._headers(account_id)).json()
            topic = next(item for item in state['topics'] if item['id'] == fixture['topic_id'])
            self.assertEqual(topic['stage'], 'decided')
            self.assertEqual(topic['attention'], 'results_available')
            self.assertTrue(topic['is_highlighted'])
            self.assertTrue(topic['is_fixture'])
            own = next(
                task
                for task in state['tasks']
                if task['topic_id'] == fixture['topic_id'] and task['assignee_id'] == account_id
            )
            tasks_by_account[account_id] = own['id']
            self.assertEqual(own['status'], 'done')
            detail = self.client.get(
                f'/api/tasks/{own["id"]}/exploration', headers=self._headers(account_id)
            )
            self.assertEqual(detail.status_code, 200, detail.text)
            self.assertEqual(len(detail.json()['topic']['directions']), 3)
            self.assertEqual(len(detail.json()['topic']['proposals']), 3)
            self.assertIn('虚拟实例', detail.json()['topic']['decision']['body'])

        cross_member = self.client.get(
            f'/api/tasks/{tasks_by_account["fixed_trial_3"]}/exploration',
            headers=self._headers('fixed_trial_2'),
        )
        self.assertEqual(cross_member.status_code, 404)

        demo_state = self.client.get(
            '/api/state', headers=self._headers('fixed_demo_jiancheng')
        ).json()
        self.assertNotIn(fixture['topic_id'], {item['id'] for item in demo_state['topics']})
        self.assertTrue(
            set(fixture['task_ids']).isdisjoint({item['id'] for item in demo_state['tasks']})
        )
        hidden = self.client.get(
            f'/api/topics/{fixture["topic_id"]}',
            headers=self._headers('fixed_demo_jiancheng'),
        )
        self.assertEqual(hidden.status_code, 404)
        hidden_task = self.client.get(
            f'/api/tasks/{tasks_by_account["fixed_trial_1"]}/exploration',
            headers=self._headers('fixed_demo_jiancheng'),
        )
        self.assertEqual(hidden_task.status_code, 404)

        immutable = self.client.post(
            f'/api/topics/{fixture["topic_id"]}/reviews',
            json={'operation_id': str(uuid4())},
            headers=self._headers('fixed_trial_2'),
        )
        self.assertEqual(immutable.status_code, 409)
        no_handoff = self.client.post(
            f'/api/topics/{fixture["topic_id"]}/handoff',
            json={
                'operation_id': str(uuid4()),
                'target_id': 'fixed_trial_2',
                'task_title': '不应创建',
            },
            headers=self._headers('fixed_trial_1'),
        )
        self.assertEqual(no_handoff.status_code, 409)

    def test_fixture_reset_is_idempotent_and_preserves_unrelated_trial_data(self):
        fixture = self._prepare().json()['exploration_fixture']
        custom_id = 'tutorial-unrelated-' + uuid4().hex[:12]
        with database.lock, database.connection() as db:
            resources.create_resource(
                db,
                'fixed_trial_1',
                '体验者自有资料',
                '重置虚拟实例不得删除。',
                scope='team',
                resource_id=custom_id,
            )

        operation_id = str(uuid4())
        payload = {'operation_id': operation_id}
        first = self.client.post(
            '/api/tutorial/exploration/reset',
            json=payload,
            headers=self._headers('fixed_trial_3'),
        )
        second = self.client.post(
            '/api/tutorial/exploration/reset',
            json=payload,
            headers=self._headers('fixed_trial_3'),
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json(), second.json())
        self.assertTrue(first.json()['reset'])
        self.assertEqual(first.json()['topic_id'], fixture['topic_id'])
        with database.lock, database.connection() as db:
            self.assertTrue(
                db.execute('SELECT 1 FROM accord_resources WHERE id=?', (custom_id,)).fetchone()
            )
            self.assertEqual(db.execute('SELECT count(*) FROM accord_index_queue').fetchone()[0], 0)
            db.execute('DELETE FROM accord_resource_versions WHERE resource_id=?', (custom_id,))
            db.execute('DELETE FROM accord_resources WHERE id=?', (custom_id,))
            index.synchronize(db)

    def test_prepare_migrates_the_exact_legacy_brand_copy(self):
        expected = tutorial.TUTORIAL_RESOURCES[2]
        legacy_body = expected.body.replace('拍办工作台', 'Accord 工作台').replace(
            '负责拍办的', '负责 Accord 的'
        )
        with database.lock, database.connection() as db:
            resources.create_resource(
                db,
                expected.owner_id,
                expected.title,
                legacy_body,
                scope='team',
                resource_id=expected.id,
            )

        prepared = self._prepare()
        self.assertEqual(prepared.status_code, 200, prepared.text)
        with database.lock:
            db = database.connection()
            current = db.execute(
                """SELECT r.version,v.title,v.body FROM accord_resources r
                JOIN accord_resource_versions v ON v.resource_id=r.id AND v.version=r.version
                WHERE r.id=?""",
                (expected.id,),
            ).fetchone()
            self.assertEqual(current['version'], 2)
            self.assertEqual(current['title'], expected.title)
            self.assertEqual(current['body'], expected.body)

    def test_prepare_migrates_the_exact_legacy_completion_copy(self):
        expected = tutorial.TUTORIAL_RESOURCES[0]
        legacy_body = expected.body.replace(
            '任务先由负责人在自己的工作台对话里完成；本人勾选后，系统直接读取这段对话、生成总结并沉淀记忆。',
            '任务完成后由负责人勾选，系统依据真实成果生成总结。',
        ).replace(
            '演示结束前是否能在体验者三的工作台对话中完成 UI 复核，再由待办整理流程直接读取结果。',
            '演示结束前是否已准备一份可上传的 UI 复核结果，供任务完成时核验。',
        )
        with database.lock, database.connection() as db:
            resources.create_resource(
                db,
                expected.owner_id,
                expected.title,
                legacy_body,
                scope='team',
                resource_id=expected.id,
            )

        prepared = self._prepare()
        self.assertEqual(prepared.status_code, 200, prepared.text)
        with database.lock:
            current = (
                database.connection()
                .execute(
                    """SELECT r.version,v.body FROM accord_resources r
                JOIN accord_resource_versions v ON v.resource_id=r.id AND v.version=r.version
                WHERE r.id=?""",
                    (expected.id,),
                )
                .fetchone()
            )
            self.assertEqual(current['version'], 2)
            self.assertEqual(current['body'], expected.body)

    def test_prepare_retires_only_generated_legacy_completion_records(self):
        legacy_id = 'legacy-completion-' + uuid4().hex[:12]
        unrelated_id = 'unrelated-completion-' + uuid4().hex[:12]
        self.addCleanup(self._remove_resources, legacy_id, unrelated_id)
        with database.lock, database.connection() as db:
            resources.create_resource(
                db,
                'fixed_trial_2',
                '拍办 90 秒开场稿 · 完成记录',
                '# 拍办 90 秒开场稿完成记录\n\n关联待办：task-old\n\n## 开场稿\n\n旧稿\n\n## 已完成\n\n- 旧教程生成',
                scope='team',
                resource_id=legacy_id,
            )
            resources.create_resource(
                db,
                'fixed_trial_2',
                '拍办 90 秒开场稿 · 完成记录',
                '这是体验者自己保存的同名资料，不包含旧教程标记。',
                scope='team',
                resource_id=unrelated_id,
            )

        prepared = self._prepare()
        self.assertEqual(prepared.status_code, 200, prepared.text)
        self.assertEqual(prepared.json()['retired_completion_count'], 1)
        with database.lock:
            db = database.connection()
            legacy = db.execute(
                'SELECT active FROM accord_resources WHERE id=?', (legacy_id,)
            ).fetchone()
            unrelated = db.execute(
                'SELECT active FROM accord_resources WHERE id=?', (unrelated_id,)
            ).fetchone()
            self.assertEqual(legacy['active'], 0)
            self.assertEqual(unrelated['active'], 1)

    def test_prepare_clears_stale_completion_before_the_next_tutorial_task(self):
        owner_id = 'fixed_trial_2'
        self.addCleanup(self._cancel_active_completion_flows, owner_id)
        created = self.client.post(
            '/api/threads',
            json={
                'operation_id': str(uuid4()),
                'target_id': owner_id,
                'title': '旧演练工作台',
            },
            headers=self._headers(owner_id),
        )
        self.assertEqual(created.status_code, 200, created.text)
        thread_id = created.json()['id']
        with database.lock, database.connection() as db:
            stale_task_id, _ = coordination_service.create_task(
                db, owner_id, owner_id, '旧演练待办', '上一轮没有完成的整理', thread_id
            )
            next_task_id, _ = coordination_service.create_task(
                db, owner_id, owner_id, '本轮演练待办', '第五步需要勾选的待办', thread_id
            )

        stale = self.client.post(
            f'/api/tasks/{stale_task_id}/tick',
            json={'operation_id': str(uuid4()), 'thread_id': thread_id},
            headers=self._headers(owner_id),
        )
        self.assertEqual(stale.status_code, 200, stale.text)
        with database.lock, database.connection() as db:
            db.execute(
                "UPDATE accord_flows SET status='error',error=? WHERE id=?",
                ('资料不存在或当前无权读取。', stale.json()['id']),
            )

        prepared = self._prepare(owner_id)
        self.assertEqual(prepared.status_code, 200, prepared.text)
        self.assertEqual(prepared.json()['cancelled_completion_count'], 1)
        stale_flow = database.query_one(
            'SELECT status,error FROM accord_flows WHERE id=?', (stale.json()['id'],)
        )
        self.assertEqual(stale_flow['status'], 'cancelled')
        self.assertEqual(stale_flow['error'], '资料不存在或当前无权读取。')

        current = self.client.post(
            f'/api/tasks/{next_task_id}/tick',
            json={'operation_id': str(uuid4()), 'thread_id': thread_id},
            headers=self._headers(owner_id),
        )
        self.assertEqual(current.status_code, 200, current.text)

    def test_fixed_account_brand_migration_updates_only_fixed_content(self):
        fixed_id = 'resource_fixed_brand_test'
        unrelated_id = 'resource_unrelated_brand_test'
        with database.lock, database.connection() as db:
            db.execute('DELETE FROM project_state WHERE key=?', (brand.MARKER,))
            resources.create_resource(
                db,
                'fixed_trial_1',
                'Accord 工作台',
                '在 Accord 中协作',
                scope='team',
                resource_id=fixed_id,
            )
            resources.create_resource(
                db,
                'member_unrelated',
                'Accord 历史资料',
                '保留 Accord 原文',
                scope='private',
                resource_id=unrelated_id,
            )

        brand.initialize()
        with database.lock, database.connection() as db:
            fixed = db.execute(
                'SELECT title,body FROM accord_resource_versions WHERE resource_id=?',
                (fixed_id,),
            ).fetchone()
            unrelated = db.execute(
                'SELECT title,body FROM accord_resource_versions WHERE resource_id=?',
                (unrelated_id,),
            ).fetchone()
            self.assertEqual(dict(fixed), {'title': '拍办工作台', 'body': '在拍办中协作'})
            self.assertEqual(
                dict(unrelated),
                {'title': 'Accord 历史资料', 'body': '保留 Accord 原文'},
            )
            for rid in (fixed_id, unrelated_id):
                db.execute('DELETE FROM accord_resource_versions WHERE resource_id=?', (rid,))
                db.execute('DELETE FROM accord_resources WHERE id=?', (rid,))

    def test_fixed_member_name_migration_updates_only_demo_content(self):
        fixed_id = 'resource_fixed_member_name_test'
        unrelated_id = 'resource_unrelated_member_name_test'
        with database.lock, database.connection() as db:
            db.execute('DELETE FROM project_state WHERE key=?', (fixed_member_names.MARKER,))
            db.execute(
                "UPDATE units SET person_name='舒奥',agent_name='舒奥的 Agent' "
                "WHERE id='fixed_demo_shuao'"
            )
            resources.create_resource(
                db,
                'fixed_demo_shuao',
                '舒奥的界面复核',
                '由舒奥完成。',
                scope='team',
                resource_id=fixed_id,
            )
            resources.create_resource(
                db,
                'member_unrelated',
                '舒奥的私人原文',
                '保留舒奥原文。',
                scope='private',
                resource_id=unrelated_id,
            )

        fixed_member_names.initialize()
        with database.lock, database.connection() as db:
            renamed_unit = db.execute(
                "SELECT person_name,agent_name FROM units WHERE id='fixed_demo_shuao'"
            ).fetchone()
            fixed = db.execute(
                'SELECT title,body FROM accord_resource_versions WHERE resource_id=?',
                (fixed_id,),
            ).fetchone()
            unrelated = db.execute(
                'SELECT title,body FROM accord_resource_versions WHERE resource_id=?',
                (unrelated_id,),
            ).fetchone()
            self.assertEqual(
                dict(renamed_unit),
                {'person_name': '书傲', 'agent_name': '书傲的 Agent'},
            )
            self.assertEqual(dict(fixed), {'title': '书傲的界面复核', 'body': '由书傲完成。'})
            self.assertEqual(
                dict(unrelated),
                {'title': '舒奥的私人原文', 'body': '保留舒奥原文。'},
            )
            for rid in (fixed_id, unrelated_id):
                db.execute('DELETE FROM accord_resource_versions WHERE resource_id=?', (rid,))
                db.execute('DELETE FROM accord_resources WHERE id=?', (rid,))

    def test_prepare_never_overwrites_a_conflicting_stable_resource(self):
        expected = tutorial.TUTORIAL_RESOURCES[0]
        with database.lock, database.connection() as db:
            resources.create_resource(
                db,
                expected.owner_id,
                '用户已有同名标识资料',
                '必须原样保留',
                scope='team',
                resource_id=expected.id,
            )

        rejected = self._prepare()
        self.assertEqual(rejected.status_code, 409)
        with database.lock:
            db = database.connection()
            current = db.execute(
                'SELECT title,body FROM accord_resource_versions WHERE resource_id=?',
                (expected.id,),
            ).fetchone()
            self.assertEqual(
                dict(current), {'title': '用户已有同名标识资料', 'body': '必须原样保留'}
            )
            self.assertEqual(
                db.execute(
                    "SELECT count(*) FROM accord_resources WHERE id LIKE 'tutorial_context_%'"
                ).fetchone()[0],
                1,
            )


if __name__ == '__main__':
    unittest.main()
