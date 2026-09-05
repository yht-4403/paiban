"""Passwordless fixed identities and tab-scoped sessions."""

import os
import tempfile
import unittest
from contextlib import contextmanager
from uuid import uuid4

_temporary = None
if 'ACCORD_DATA_DIR' not in os.environ:
    _temporary = tempfile.TemporaryDirectory(prefix='accord-fixed-accounts-test-')
    os.environ['ACCORD_DATA_DIR'] = _temporary.name

from fastapi.testclient import TestClient  # noqa: E402

from accord_api.app import app  # noqa: E402
from accord_api.modules.coordination import service as coordination  # noqa: E402
from accord_api.modules.identity import service  # noqa: E402
from accord_api.modules.knowledge import index, resources, retrieval  # noqa: E402
from accord_api.modules.permissions import policy as access  # noqa: E402
from accord_api.platform.db import database  # noqa: E402
from accord_api.platform.errors import DomainError  # noqa: E402


class FixedAccountTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()

    @contextmanager
    def legacy_identity(self):
        uid = 'member_legacy_' + uuid4().hex[:12]
        token = ''
        with database.lock, database.connection() as db:
            now = database.now()
            db.execute(
                'INSERT INTO units(id,person_name,agent_name,created_at) VALUES(?,?,?,?)',
                (uid, '历史验收账号', '历史验收账号的 Agent', now),
            )
            db.execute(
                'INSERT INTO accord_accounts VALUES(?,?,?,?,?)',
                (
                    uid,
                    f'{uid}@example.test',
                    service.FIXED_PASSWORD_HASH,
                    'member',
                    now,
                ),
            )
        try:
            token = service.start_session(uid)
            yield uid, token
        finally:
            if token:
                service.logout(token=token)
            with database.lock, database.connection() as db:
                resource_ids = [
                    row['id']
                    for row in db.execute(
                        'SELECT id FROM accord_resources WHERE owner_id=?', (uid,)
                    ).fetchall()
                ]
                for rid in resource_ids:
                    db.execute('DELETE FROM accord_resource_versions WHERE resource_id=?', (rid,))
                    db.execute('DELETE FROM accord_resources WHERE id=?', (rid,))
                index.synchronize(db)
                db.execute('DELETE FROM accord_operations WHERE actor=?', (uid,))
                db.execute('DELETE FROM accord_accounts WHERE unit_id=?', (uid,))
                db.execute('DELETE FROM units WHERE id=?', (uid,))

    def test_account_catalog_is_stable_and_does_not_expose_credentials(self):
        first = self.client.get('/api/auth/accounts')
        second = self.client.get('/api/auth/accounts')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), second.json())
        accounts = first.json()['accounts']
        self.assertEqual(
            [account['id'] for account in accounts],
            [
                'fixed_demo_jiancheng',
                'fixed_demo_baotian',
                'fixed_demo_shuao',
                'fixed_trial_1',
                'fixed_trial_2',
                'fixed_trial_3',
            ],
        )
        self.assertEqual(
            [account['name'] for account in accounts],
            ['建成', '堡天', '舒奥', '体验者一', '体验者二', '体验者三'],
        )
        self.assertEqual([account['kind'] for account in accounts], ['demo'] * 3 + ['trial'] * 3)
        self.assertTrue(all('email' not in account for account in accounts))
        self.assertTrue(all('password' not in account for account in accounts))

    def test_only_catalog_accounts_can_create_a_passwordless_session(self):
        rejected = self.client.post('/api/auth/select', json={'account_id': 'member_arbitrary'})
        self.assertEqual(rejected.status_code, 404)

        selected = self.client.post('/api/auth/select', json={'account_id': 'fixed_demo_jiancheng'})
        self.assertEqual(selected.status_code, 200)
        token = selected.json()['session_token']
        self.assertGreater(len(token), 32)
        self.assertNotIn(service.COOKIE, self.client.cookies)

        state = self.client.get('/api/state', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(state.status_code, 200)
        self.assertEqual(state.json()['me'], 'fixed_demo_jiancheng')
        self.assertEqual(state.json()['account']['email'], '')
        self.assertEqual(
            [member['id'] for member in state.json()['members']],
            ['fixed_demo_jiancheng', 'fixed_demo_baotian', 'fixed_demo_shuao'],
        )

    def test_bearer_sessions_keep_two_windows_on_different_identities(self):
        tokens = {}
        for account_id in ('fixed_demo_baotian', 'fixed_demo_shuao'):
            response = self.client.post('/api/auth/select', json={'account_id': account_id})
            tokens[account_id] = response.json()['session_token']

        for account_id, token in tokens.items():
            response = self.client.get('/api/state', headers={'Authorization': f'Bearer {token}'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['me'], account_id)

        logged_out = self.client.post(
            '/api/auth/logout',
            headers={'Authorization': f'Bearer {tokens["fixed_demo_baotian"]}'},
        )
        self.assertEqual(logged_out.status_code, 200)
        self.assertEqual(
            self.client.get(
                '/api/state',
                headers={'Authorization': f'Bearer {tokens["fixed_demo_baotian"]}'},
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.get(
                '/api/state',
                headers={'Authorization': f'Bearer {tokens["fixed_demo_shuao"]}'},
            ).status_code,
            200,
        )

    def test_bearer_identity_takes_precedence_over_the_compatibility_cookie(self):
        cookie_token = service.start_session('fixed_trial_1')
        bearer_token = service.start_session('fixed_trial_2')
        self.client.cookies.set(service.COOKIE, cookie_token, path='/api')

        state = self.client.get('/api/state', headers={'Authorization': f'Bearer {bearer_token}'})
        self.assertEqual(state.status_code, 200)
        self.assertEqual(state.json()['me'], 'fixed_trial_2')
        self.assertEqual(
            self.client.get('/api/state', headers={'Authorization': 'not-bearer'}).status_code,
            401,
        )

    def test_fixed_accounts_are_preseeded_without_a_usable_password(self):
        service.initialize_fixed_accounts()
        service.initialize_fixed_accounts()
        rows = database.query(
            'SELECT unit_id,email,password_hash FROM accord_accounts WHERE unit_id LIKE ?',
            ('fixed_%',),
        )
        self.assertEqual(len(rows), 6)
        self.assertEqual({row['unit_id'] for row in rows}, set(service.FIXED_ACCOUNT_IDS))
        self.assertTrue(all(row['email'].endswith('@accord.invalid') for row in rows))
        self.assertTrue(all(row['password_hash'] == service.FIXED_PASSWORD_HASH for row in rows))

        status = self.client.get('/api/auth/status').json()
        self.assertEqual(status['auth_mode'], 'fixed_accounts')
        self.assertFalse(status['needs_setup'])

    def test_team_resources_are_invisible_across_fixed_and_legacy_rosters(self):
        fixed = 'fixed_demo_jiancheng'
        marker = uuid4().hex
        created = []
        fixed_token = service.start_session(fixed)
        with self.legacy_identity() as (legacy, legacy_token):
            try:
                with database.lock, database.connection() as db:
                    fixed_rid = resources.create_resource(
                        db, fixed, '固定账号资料', 'fixed-' + marker, scope='team'
                    )
                    legacy_rid = resources.create_resource(
                        db, legacy, '历史账号资料', 'legacy-' + marker, scope='team'
                    )
                    created.extend((fixed_rid, legacy_rid))
                    index.synchronize(db)
                    fixed_resource = db.execute(
                        'SELECT * FROM accord_resources WHERE id=?', (fixed_rid,)
                    ).fetchone()
                    legacy_resource = db.execute(
                        'SELECT * FROM accord_resources WHERE id=?', (legacy_rid,)
                    ).fetchone()

                    self.assertFalse(access.can_read(db, legacy, fixed_resource))
                    self.assertFalse(access.can_read(db, fixed, legacy_resource))
                    self.assertNotIn(
                        fixed_rid, {item['id'] for item in resources.available(db, legacy)}
                    )
                    self.assertNotIn(
                        legacy_rid, {item['id'] for item in resources.available(db, fixed)}
                    )
                    with self.assertRaises(DomainError):
                        access.resource_for(db, legacy, fixed_rid)
                    with self.assertRaises(DomainError):
                        access.resource_for(db, fixed, legacy_rid)
                    self.assertEqual(retrieval.search(db, fixed, [legacy], marker)['sources'], [])
                    self.assertEqual(retrieval.search(db, legacy, [fixed], marker)['sources'], [])
                    self.assertTrue(retrieval.search(db, fixed, [fixed], marker)['sources'])
                    self.assertTrue(retrieval.search(db, legacy, [legacy], marker)['sources'])

                fixed_state = self.client.get(
                    '/api/state', headers={'Authorization': f'Bearer {fixed_token}'}
                ).json()
                legacy_state = self.client.get(
                    '/api/state', headers={'Authorization': f'Bearer {legacy_token}'}
                ).json()
                self.assertIn(fixed_rid, {item['id'] for item in fixed_state['documents']})
                self.assertNotIn(legacy_rid, {item['id'] for item in fixed_state['documents']})
                self.assertIn(legacy_rid, {item['id'] for item in legacy_state['documents']})
                self.assertNotIn(fixed_rid, {item['id'] for item in legacy_state['documents']})
            finally:
                service.logout(token=fixed_token)
                with database.lock, database.connection() as db:
                    for rid in created:
                        db.execute(
                            'DELETE FROM accord_resource_versions WHERE resource_id=?', (rid,)
                        )
                        db.execute('DELETE FROM accord_resources WHERE id=?', (rid,))
                    index.synchronize(db)

    def test_demo_and_trial_accounts_have_separate_members_and_team_resources(self):
        demo = 'fixed_demo_jiancheng'
        trial = 'fixed_trial_1'
        marker = uuid4().hex
        created = []
        demo_token = service.start_session(demo)
        trial_token = service.start_session(trial)
        try:
            with database.lock, database.connection() as db:
                demo_rid = resources.create_resource(
                    db, demo, '演示组资料', 'demo-' + marker, scope='team'
                )
                trial_rid = resources.create_resource(
                    db, trial, '体验组资料', 'trial-' + marker, scope='team'
                )
                created.extend((demo_rid, trial_rid))
                index.synchronize(db)

                self.assertNotIn(trial_rid, {item['id'] for item in resources.available(db, demo)})
                self.assertNotIn(demo_rid, {item['id'] for item in resources.available(db, trial)})
                self.assertEqual(retrieval.search(db, trial, [demo], marker)['sources'], [])
                self.assertEqual(retrieval.search(db, demo, [trial], marker)['sources'], [])

            demo_state = self.client.get(
                '/api/state', headers={'Authorization': f'Bearer {demo_token}'}
            ).json()
            trial_state = self.client.get(
                '/api/state', headers={'Authorization': f'Bearer {trial_token}'}
            ).json()
            self.assertEqual(
                [member['id'] for member in demo_state['members']],
                ['fixed_demo_jiancheng', 'fixed_demo_baotian', 'fixed_demo_shuao'],
            )
            self.assertEqual(
                [member['id'] for member in trial_state['members']],
                ['fixed_trial_1', 'fixed_trial_2', 'fixed_trial_3'],
            )
            self.assertIn(demo_rid, {item['id'] for item in demo_state['documents']})
            self.assertNotIn(trial_rid, {item['id'] for item in demo_state['documents']})
            self.assertIn(trial_rid, {item['id'] for item in trial_state['documents']})
            self.assertNotIn(demo_rid, {item['id'] for item in trial_state['documents']})

            blocked = self.client.post(
                '/api/chats/open',
                json={'operation_id': uuid4().hex, 'target_id': trial},
                headers={'Authorization': f'Bearer {demo_token}'},
            )
            self.assertEqual(blocked.status_code, 404)
            blocked_group = self.client.post(
                '/api/groups',
                json={
                    'operation_id': uuid4().hex,
                    'member_ids': ['fixed_demo_baotian', trial],
                },
                headers={'Authorization': f'Bearer {demo_token}'},
            )
            self.assertEqual(blocked_group.status_code, 404)
            blocked_meeting = self.client.post(
                '/api/flows',
                json={
                    'operation_id': uuid4().hex,
                    'kind': 'sync',
                    'title': '隔离验收会议',
                    'body': '体验账号不得进入演示会议。',
                    'member_ids': [trial],
                },
                headers={'Authorization': f'Bearer {demo_token}'},
            )
            self.assertEqual(blocked_meeting.status_code, 422)
            with self.assertRaises(DomainError):
                coordination.create_task(database.connection(), demo, trial, '跨组待办', '不应创建')
        finally:
            service.logout(token=demo_token)
            service.logout(token=trial_token)
            with database.lock, database.connection() as db:
                for rid in created:
                    db.execute('DELETE FROM accord_resource_versions WHERE resource_id=?', (rid,))
                    db.execute('DELETE FROM accord_resources WHERE id=?', (rid,))
                index.synchronize(db)

    def test_cross_roster_collaboration_targets_are_rejected(self):
        fixed = 'fixed_demo_jiancheng'
        fixed_token = service.start_session(fixed)
        fixed_headers = {'Authorization': f'Bearer {fixed_token}'}
        with self.legacy_identity() as (legacy, legacy_token):
            legacy_headers = {'Authorization': f'Bearer {legacy_token}'}

            def operation():
                return uuid4().hex

            self.assertEqual(
                self.client.post(
                    '/api/chats/open',
                    json={'operation_id': operation(), 'target_id': legacy},
                    headers=fixed_headers,
                ).status_code,
                404,
            )
            self.assertEqual(
                self.client.post(
                    '/api/chats/open',
                    json={'operation_id': operation(), 'target_id': fixed},
                    headers=legacy_headers,
                ).status_code,
                404,
            )
            self.assertEqual(
                self.client.post(
                    '/api/groups',
                    json={
                        'operation_id': operation(),
                        'member_ids': ['fixed_demo_baotian', legacy],
                    },
                    headers=fixed_headers,
                ).status_code,
                404,
            )
            self.assertEqual(
                self.client.post(
                    '/api/flows',
                    json={
                        'operation_id': operation(),
                        'kind': 'sync',
                        'title': '跨组流程',
                        'body': '不应创建',
                        'member_ids': [legacy],
                    },
                    headers=fixed_headers,
                ).status_code,
                422,
            )
            self.assertEqual(
                self.client.post(
                    '/api/topics',
                    json={
                        'operation_id': operation(),
                        'title': '跨组课题',
                        'brief': '不应创建',
                        'member_ids': [legacy],
                    },
                    headers=fixed_headers,
                ).status_code,
                404,
            )
            self.assertEqual(
                self.client.get(
                    f'/api/members/{legacy}/activity', headers=fixed_headers
                ).status_code,
                404,
            )
            self.assertEqual(
                self.client.get(
                    f'/api/members/{fixed}/activity', headers=legacy_headers
                ).status_code,
                404,
            )
            with self.assertRaises(DomainError):
                coordination.create_task(
                    database.connection(), fixed, legacy, '跨组待办', '不应创建'
                )
        service.logout(token=fixed_token)


if __name__ == '__main__':
    unittest.main()
