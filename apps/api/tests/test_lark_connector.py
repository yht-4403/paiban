"""External source synchronization, versioning and permission boundaries."""

import unittest
from unittest.mock import patch
from uuid import uuid4

import test_collaboration as fixtures

from accord_api.modules.knowledge import connectors
from accord_api.platform.db import database as store
from accord_api.platform.errors import DomainError


class LarkConnectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not hasattr(fixtures.CollaborationTests, 'ids'):
            fixtures.CollaborationTests.setUpClass()
        cls.clients, cls.ids = fixtures.CollaborationTests.clients, fixtures.CollaborationTests.ids

    def post(self, who, path, body=None, status=200):
        response = self.clients[who].post(
            '/api' + path, json={**(body or {}), 'operation_id': str(uuid4())}
        )
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    def remote(self, marker, revision='1', external_id=None):
        content = '飞书连接器验收 ' + marker
        return {
            'external_id': external_id or 'doc_' + uuid4().hex,
            'revision': revision,
            'title': '连接器验收文档',
            'content': content,
            'digest': connectors.hashlib.sha256(
                ('连接器验收文档\n' + content).encode()
            ).hexdigest(),
        }

    def test_owner_connects_private_source_then_explicitly_shares_and_disconnects(self):
        remote = self.remote(uuid4().hex)
        with patch.object(connectors, 'fetch_lark_document', return_value=remote):
            connection = self.post(
                'lin',
                '/knowledge/connections/lark',
                {'url': 'https://example.feishu.cn/docx/' + remote['external_id']},
            )
        self.assertEqual(connection['scope'], 'private')
        self.assertEqual(connection['status'], 'ready')
        resource_id = connection['resource_id']
        self.assertEqual(
            self.clients['su'].get('/api/resources/' + resource_id).status_code, 404
        )
        shared = self.post(
            'lin',
            f"/knowledge/connections/{connection['id']}/scope",
            {'expected_version': connection['version'], 'scope': 'team'},
        )
        self.assertEqual(shared['scope'], 'team')
        self.assertEqual(
            self.clients['su'].get('/api/resources/' + resource_id).json()['body'],
            remote['content'],
        )
        disconnected = self.post(
            'lin',
            f"/knowledge/connections/{connection['id']}/disconnect",
            {'expected_version': shared['version']},
        )
        self.assertFalse(disconnected['enabled'])
        self.assertEqual(disconnected['status'], 'disconnected')
        self.assertEqual(
            self.clients['lin'].get('/api/resources/' + resource_id).status_code, 200
        )

    def test_sync_preserves_versions_and_previous_content_on_failure(self):
        external_id = 'doc_' + uuid4().hex
        first = self.remote('第一版', external_id=external_id)
        with patch.object(connectors, 'fetch_lark_document', return_value=first):
            connection = self.post(
                'lin',
                '/knowledge/connections/lark',
                {'url': 'https://example.feishu.cn/docx/' + external_id},
            )
            unchanged = self.post(
                'lin',
                f"/knowledge/connections/{connection['id']}/sync",
                {'expected_version': connection['version']},
            )
        self.assertEqual(unchanged['resource_version'], 1)
        second = self.remote('第二版', revision='2', external_id=external_id)
        with patch.object(connectors, 'fetch_lark_document', return_value=second):
            changed = self.post(
                'lin',
                f"/knowledge/connections/{connection['id']}/sync",
                {'expected_version': unchanged['version']},
            )
        self.assertEqual(changed['resource_version'], 2)
        self.assertEqual(
            self.clients['lin'].get(
                '/api/resources/' + connection['resource_id'] + '?version=1'
            ).json()['body'],
            first['content'],
        )
        with patch.object(
            connectors,
            'fetch_lark_document',
            side_effect=DomainError(503, '暂时不可用'),
        ):
            self.post(
                'lin',
                f"/knowledge/connections/{connection['id']}/sync",
                {'expected_version': changed['version']},
                status=503,
            )
        state = self.clients['lin'].get('/api/state').json()
        current = next(c for c in state['content_connections'] if c['id'] == connection['id'])
        self.assertEqual(current['status'], 'error')
        self.assertEqual(
            self.clients['lin'].get('/api/resources/' + connection['resource_id']).json()['body'],
            second['content'],
        )

    def test_member_cannot_use_machine_identity_and_background_refresh_is_claimed(self):
        self.post(
            'su',
            '/knowledge/connections/lark',
            {'url': 'https://example.feishu.cn/docx/forbidden'},
            status=403,
        )
        self.post(
            'lin',
            '/knowledge/connections/lark',
            {'url': 'https://example.com/docx/not-lark'},
            status=422,
        )
        external_id = 'doc_' + uuid4().hex
        first = self.remote('后台第一版', external_id=external_id)
        with patch.object(connectors, 'fetch_lark_document', return_value=first):
            connection = self.post(
                'lin',
                '/knowledge/connections/lark',
                {'url': 'https://example.feishu.cn/docx/' + external_id},
            )
        second = self.remote('后台第二版', revision='2', external_id=external_id)
        with patch.object(connectors, 'fetch_lark_document', return_value=second):
            connectors.sync_due(connection['id'])
        row = store.query_one(
            'SELECT status,version FROM accord_content_connections WHERE id=?',
            (connection['id'],),
        )
        self.assertEqual(row['status'], 'ready')
        self.assertGreater(row['version'], connection['version'])
        self.assertEqual(
            self.clients['lin'].get('/api/resources/' + connection['resource_id']).json()['body'],
            second['content'],
        )


if __name__ == '__main__':
    unittest.main()
