"""Guided trial preparation creates only searchable shared reference material."""

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
from accord_api.modules.identity import service as identity  # noqa: E402
from accord_api.modules.knowledge import index, resources, retrieval  # noqa: E402
from accord_api.modules.tutorial import service as tutorial  # noqa: E402
from accord_api.platform.db import database  # noqa: E402


class TutorialPreparationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self._remove_tutorial_resources()
        self.tokens = {
            account_id: self.client.post(
                '/api/auth/select', json={'account_id': account_id}
            ).json()['session_token']
            for account_id in ('fixed_demo_jiancheng', 'fixed_trial_1', 'fixed_trial_2')
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
            for item in tutorial.TUTORIAL_RESOURCES:
                db.execute('DELETE FROM accord_resource_versions WHERE resource_id=?', (item.id,))
                db.execute('DELETE FROM accord_resources WHERE id=?', (item.id,))
            index.synchronize(db)
            for item in tutorial.TUTORIAL_RESOURCES:
                db.execute(
                    'DELETE FROM accord_content_chunks WHERE source_key=?',
                    ('resource:' + item.id,),
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
                db.execute('SELECT count(*) FROM accord_resources').fetchone()[0], before + 3
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

    def test_prepare_creates_no_chat_model_meeting_task_or_completion_state(self):
        business_tables = (
            'accord_threads',
            'messages',
            'handoffs',
            'accord_runs',
            'accord_tool_calls',
            'accord_flows',
            'accord_flow_actions',
            'tasks',
            'accord_task_acl',
            'accord_rounds',
            'accord_proposals',
            'artifacts',
            'memories',
            'meeting_msgs',
        )
        with database.lock:
            db = database.connection()
            before = {
                table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                for table in business_tables
            }

        prepared = self._prepare()
        self.assertEqual(prepared.status_code, 200)
        self.assertEqual(len(prepared.json()['resources']), 3)

        with database.lock:
            db = database.connection()
            after = {
                table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                for table in business_tables
            }
            self.assertEqual(after, before)
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
