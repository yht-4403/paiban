import json
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_collaboration as fixtures
import test_workflows as workflows

from accord_api.modules.collaboration.repository import message
from accord_api.modules.coordination import generation, service, task_completion
from accord_api.platform.ai.errors import ModelError
from accord_api.platform.db import database as store


class TaskCompletionTests(unittest.TestCase):
    post = workflows.WorkflowTests.post
    get = workflows.WorkflowTests.get

    @classmethod
    def setUpClass(cls):
        if not hasattr(fixtures.CollaborationTests, 'ids'):
            fixtures.CollaborationTests.setUpClass()
        cls.clients, cls.ids = fixtures.CollaborationTests.clients, fixtures.CollaborationTests.ids

    def setUp(self):
        self.addCleanup(
            lambda: store.execute(
                "UPDATE accord_flows SET status='cancelled' WHERE kind='task_summary' AND status!='closed'"
            )
        )
        self.tid = self.post(
            'su', '/threads', {'target_id': self.ids['su'], 'title': '验收个人工作台'}
        )['id']
        with store.lock, store.connection() as db:
            self.task, _ = service.create_task(
                db, self.ids['su'], self.ids['su'], '完成接口验收', '检查 3 项边界', self.tid
            )

    def tick(self):
        return self.post('su', f'/tasks/{self.task}/tick', {'thread_id': self.tid})['id']

    def run_summary(self, fid, **outcome):
        def model(messages, cancelled, effort, tool=None, on_usage=None):
            self.assertIsNotNone(tool)
            tool.execute(uuid4().hex, 'person_context', {'query': ''})
            return json.dumps(outcome, ensure_ascii=False)

        with patch.object(generation, 'model', side_effect=model):
            generation.execute(fid)
        return self.get('su', '/flows/' + fid)

    def status(self):
        return store.query_one('SELECT status FROM tasks WHERE id=?', (self.task,))['status']

    def test_tick_summarizes_in_same_private_thread_and_saves_once(self):
        with store.lock, store.connection() as db:
            message(db, self.tid, 'human', self.ids['su'], '接口验收 3 项均已通过。')
        self.post('lin', f'/tasks/{self.task}/tick', {'thread_id': self.tid}, status=404)
        fid = self.tick()
        self.assertEqual(self.tick(), fid)
        self.assertEqual(self.status(), 'open')
        result = self.run_summary(fid, found=True, summary='接口验收 3 项通过。')
        self.assertEqual(result['status'], 'closed')
        self.assertEqual(self.status(), 'done')
        self.assertEqual(result['thread_id'], self.tid)
        memory = store.query_one(
            'SELECT resource_id FROM accord_flow_memories WHERE flow_id=?', (fid,)
        )
        self.assertEqual(self.get('su', '/resources/' + memory['resource_id'])['scope'], 'private')
        self.get('lin', '/flows/' + fid, 404)
        self.get('lin', '/threads/' + self.tid, 404)
        self.assertEqual(self.tick(), fid)
        self.assertEqual(
            len(store.query('SELECT * FROM accord_flow_memories WHERE flow_id=?', (fid,))), 1
        )
        self.assertTrue(
            any(
                '接口验收 3 项通过' in m['body']
                for m in self.get('su', '/threads/' + self.tid)['messages']
            )
        )

    def test_missing_context_asks_without_completing_and_unrelated_reply_does_not_finish(self):
        fid = self.tick()
        self.run_summary(fid, found=False, question='接口验收结果是什么？')
        self.assertEqual(self.status(), 'open')
        self.post('su', '/threads/' + self.tid + '/messages', {'body': '无关问题'}, status=409)
        self.post('lin', f'/task-summaries/{fid}/reply', {'body': '通过'}, status=404)
        self.post('su', f'/task-summaries/{fid}/reply', {'body': '今天穿白衣服'})
        self.run_summary(fid, found=False, question='这次接口验收通过了几项？')
        self.assertEqual(self.status(), 'open')
        self.post('su', f'/task-summaries/{fid}/reply', {'body': '接口 3 项均通过了'})
        self.run_summary(fid, found=True, summary='接口 3 项通过。')
        self.assertEqual(self.status(), 'done')

    def test_failure_retry_and_cancellation_do_not_complete(self):
        fid = self.tick()
        with patch.object(generation, 'model', side_effect=ModelError('upstream', '模型不可用')):
            generation.execute(fid)
        self.assertEqual(self.get('su', '/flows/' + fid)['status'], 'error')
        self.assertEqual(self.status(), 'open')
        self.post('su', f'/task-summaries/{fid}/retry')
        self.run_summary(fid, found=False, cancelled=True, summary='', question='')
        self.assertEqual(self.get('su', '/flows/' + fid)['status'], 'cancelled')
        self.assertEqual(self.status(), 'open')
        fid = self.tick()
        self.post('su', f'/task-summaries/{fid}/cancel')
        generation.execute(fid)
        self.assertEqual(self.status(), 'open')
        self.assertFalse(store.query('SELECT * FROM accord_flow_memories WHERE flow_id=?', (fid,)))

    def test_shared_workspace_rejected_and_restart_message_recovers(self):
        self.post(
            'su',
            '/context-sharing',
            {'source_kind': 'conversation', 'source_id': self.tid, 'enabled': True},
        )
        self.post('su', f'/tasks/{self.task}/tick', {'thread_id': self.tid}, status=409)
        result = self.post('su', f'/tasks/{self.task}/tick', {})
        self.assertNotEqual(result['thread_id'], self.tid)
        store.execute(
            "UPDATE accord_flows SET status='error',error='服务重启，请重试' WHERE id=?",
            (result['id'],),
        )
        task_completion.recover()
        latest = self.get('su', '/threads/' + result['thread_id'])['messages'][-1]
        self.assertEqual(latest['meta']['status'], 'error')
        self.assertEqual(self.status(), 'open')


if __name__ == '__main__':
    unittest.main()
