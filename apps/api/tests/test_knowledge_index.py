"""Ingestion, historical retrieval, provenance and permission regression tests."""

import json
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_collaboration as fixtures
import test_workflows as workflows

from accord_api.modules.agent_runs import service as runs
from accord_api.modules.collaboration.repository import message
from accord_api.modules.knowledge import ToolContext, index, person_context, retrieval
from accord_api.platform.db import database as store
from accord_api.platform.errors import DomainError


class KnowledgeIndexTests(unittest.TestCase):
    post = workflows.WorkflowTests.post
    get = workflows.WorkflowTests.get
    thread = workflows.WorkflowTests.thread
    send = workflows.WorkflowTests.send
    resource = workflows.WorkflowTests.resource

    @classmethod
    def setUpClass(cls):
        if not hasattr(fixtures.CollaborationTests, 'ids'):
            fixtures.CollaborationTests.setUpClass()
        cls.clients, cls.ids = fixtures.CollaborationTests.clients, fixtures.CollaborationTests.ids

    def test_import_batch_is_private_idempotent_versioned_and_atomic(self):
        name = uuid4().hex + '.md'
        body = {'files': [{'filename': name, 'content': '导入的中文验收标记'}]}
        first = self.post('lin', '/knowledge/imports', body)['files'][0]
        second = self.post('lin', '/knowledge/imports', body)['files'][0]
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(second['status'], 'unchanged')
        self.assertEqual(self.get('lin', '/resources/' + first['id'])['scope'], 'private')
        self.get('su', '/resources/' + first['id'], 404)
        other = uuid4().hex + '.txt'
        self.post(
            'lin',
            '/knowledge/imports',
            {
                'files': [
                    {'filename': other, 'content': '不得部分提交'},
                    {'filename': name, 'content': '冲突正文'},
                ]
            },
            status=409,
        )
        self.assertFalse(
            store.query_one('SELECT 1 FROM accord_content_imports WHERE filename=?', (other,))
        )
        update = {
            'files': [
                {
                    'filename': name,
                    'content': '第二版',
                    'resource_id': first['id'],
                    'expected_version': 1,
                }
            ]
        }
        self.assertEqual(self.post('lin', '/knowledge/imports', update)['files'][0]['version'], 2)
        self.assertEqual(
            self.get('lin', '/resources/' + first['id'] + '?version=1')['body'],
            '导入的中文验收标记',
        )
        self.post('lin', '/knowledge/imports', update, status=409)
        for bad in (
            {'filename': '../secret.txt', 'content': '路径'},
            {'filename': 'data.pdf', 'content': '二进制'},
            {'filename': 'x.txt', 'content': '\0'},
        ):
            self.post('lin', '/knowledge/imports', {'files': [bad]}, status=422)

    def test_old_message_and_late_document_chunk_are_searchable(self):
        marker = 'buried' + uuid4().hex
        tid = self.thread()
        with store.lock, store.connection() as db:
            mid = message(db, tid, 'human', self.ids['lin'], marker + ' 已验证的历史结论')
            for n in range(30):
                message(db, tid, 'human', self.ids['lin'], f'后来的无关讨论 {n}')
        hits = self.get('lin', '/knowledge/search?q=' + marker)['sources']
        self.assertTrue(any(r['message_id'] == mid for r in hits))
        rid = self.resource(body='无关背景。' * 1600 + '中文深处标记')
        hits = self.get('lin', '/knowledge/search?q=深处标记')['sources']
        found = next(r for r in hits if r['id'] == rid)
        self.assertGreater(found['offset'], 4000)
        self.assertIn('深处标记', self.get('lin', '/knowledge/chunks/' + found['chunk_id'])['body'])
        self.get('su', '/knowledge/chunks/' + found['chunk_id'], 404)

    def test_index_is_incremental_and_permissions_are_live(self):
        marker = 'scoped' + uuid4().hex
        tid = self.thread()
        with store.lock, store.connection() as db:
            message(db, tid, 'human', self.ids['lin'], marker)
        audience = [self.ids['lin'], self.ids['su'], self.ids['zhou']]
        db = store.connection()
        self.assertFalse(retrieval.search(db, self.ids['lin'], audience, marker)['sources'])
        self.post(
            'lin',
            '/context-sharing',
            {'source_kind': 'conversation', 'source_id': tid, 'enabled': True},
        )
        found = retrieval.search(db, self.ids['lin'], audience, marker)['sources'][0]
        index.synchronize(db)
        count = store.query_one('SELECT count(*) n FROM accord_content_chunks')['n']
        index.synchronize(db)
        self.assertEqual(
            count, store.query_one('SELECT count(*) n FROM accord_content_chunks')['n']
        )
        self.post(
            'lin',
            '/context-sharing',
            {'source_kind': 'conversation', 'source_id': tid, 'enabled': False},
        )
        with self.assertRaises(DomainError):
            person_context.validate(db, [found], audience)
        self.get('su', '/knowledge/chunks/' + found['chunk_id'], 404)
        self.post('lin', f'/threads/{tid}/archive', {'archived': True})
        self.assertFalse(
            retrieval.search(db, self.ids['lin'], [self.ids['lin']], marker)['sources']
        )

    def test_shared_chat_cannot_launder_private_document_or_nested_answer(self):
        marker = 'nested' + uuid4().hex
        rid = self.resource(body=marker)
        tid = self.thread()
        with store.lock, store.connection() as db:
            message(db, tid, 'human', self.ids['lin'], marker, [rid])
        self.post(
            'lin',
            '/context-sharing',
            {'source_kind': 'conversation', 'source_id': tid, 'enabled': True},
        )
        self.assertFalse(
            retrieval.search(store.connection(), self.ids['lin'], [self.ids['su']], marker)[
                'sources'
            ]
        )
        source = retrieval.search(store.connection(), self.ids['lin'], [self.ids['lin']], marker)[
            'sources'
        ][0]
        other = self.thread()
        with store.lock, store.connection() as db:
            message(
                db,
                other,
                'agent',
                self.ids['lin'],
                marker + ' 转述',
                meta={'status': 'done', 'context_sources': [retrieval.public_ref(source)]},
            )
        self.post(
            'lin',
            '/context-sharing',
            {'source_kind': 'conversation', 'source_id': other, 'enabled': True},
        )
        self.assertFalse(
            retrieval.search(store.connection(), self.ids['lin'], [self.ids['su']], marker)[
                'sources'
            ]
        )

    def test_tools_persist_evidence_and_exclude_current_thread_and_selected_scope(self):
        marker = 'linked' + uuid4().hex
        old = self.thread()
        with store.lock, store.connection() as db:
            message(db, old, 'human', self.ids['lin'], marker)
        tid = self.thread()
        rid = self.send('lin', tid, body=marker, execute=False)

        def answer(*args, **kwargs):
            tool = kwargs['tool_context']
            result = tool.execute('evidence', 'person_context', {'query': marker})
            self.assertIn(old, json.dumps(result))
            self.assertNotIn(tid, json.dumps(result))
            return {
                'body': '已查到历史结论',
                'sources': [],
                'usage': {},
                'model': 'test',
                'finish_reason': 'stop',
                'duration_ms': 1,
            }

        with patch('accord_api.modules.agent_runs.service.agent.stream_answer', side_effect=answer):
            runs.execute_run(rid)
        data = self.get('lin', '/threads/' + tid)
        agent = next(m for m in data['messages'] if m['from_kind'] == 'agent')
        self.assertTrue(agent['meta']['context_sources'])
        self.post('lin', f'/threads/{old}/archive', {'archived': True})
        self.assertEqual(
            self.get('lin', '/threads/' + tid)['messages'][-1]['body'], '引用内容已收回。'
        )
        self.post('lin', f'/threads/{tid}/messages', {'body': '继续用刚才的内容'}, status=404)
        folder = self.post('lin', '/folders', {'name': '空范围'})['id']
        narrowed = self.thread(folder)
        run = self.send('lin', narrowed, execute=False)
        try:
            manifest = json.loads(
                store.query_one('SELECT manifest FROM accord_run_inputs WHERE run_id=?', (run,))[
                    'manifest'
                ]
            )
            result = ToolContext(run, manifest).execute(
                'bounded', 'person_context', {'query': marker}
            )
            self.assertEqual(result['sources'], [])
        finally:
            self.post('lin', f'/runs/{run}/stop')
