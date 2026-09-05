import concurrent.futures
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import patch

_temporary = tempfile.TemporaryDirectory(prefix='accord-test-')
os.environ['ACCORD_DATA_DIR'] = _temporary.name
os.environ['ACCORD_DEMO'] = '1'
from fastapi.testclient import TestClient
from accord_api.app import app
from accord_api import store


class CollaborationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.headers = {}
        for uid in ('lin','su','zhou'):
            token = cls.client.post('/api/demo/login',json={'unit_id':uid}).json()['token']
            cls.headers[uid] = {'Authorization':'Bearer '+token}

    def post(self, uid, path, body=None, operation=None):
        return self.client.post('/api'+path,headers=self.headers[uid],json={**(body or {}),'operation_id':operation or str(uuid4())})

    def state(self,uid):
        return self.client.get('/api/state',headers=self.headers[uid]).json()

    def start(self):
        response = self.post('lin','/threads',{'target_id':'su'})
        self.assertEqual(response.status_code,200)
        return response.json()['id']

    def send(self,tid,body='工作台 UI 接入使用什么？',uid='lin',operation=None):
        return self.post(uid,f'/threads/{tid}/messages',{'body':body},operation)

    def handoff(self,tid):
        self.assertEqual(self.send(tid).status_code,200)
        result=self.post('lin',f'/threads/{tid}/handoff',{'mode':'now','note':'需要你确认'})
        self.assertEqual(result.status_code,200)

    def test_anonymous_and_legacy_routes_are_closed(self):
        self.assertEqual(self.client.get('/api/state').status_code,401)
        self.assertEqual(self.client.get('/api/threads/welcome_review').status_code,401)
        self.assertEqual(self.client.post('/api/tasks/any/status',json={'status':'done','operation_id':str(uuid4())}).status_code,401)
        for path in ['/api/snapshot','/api/decisions/any/close','/ws']:
            self.assertEqual(self.client.get(path).status_code,404)

    def test_agent_channel_is_private_until_explicit_handoff(self):
        tid=self.start()
        self.send(tid)
        for uid in ('su','zhou'):
            self.assertNotIn(tid,[t['id'] for t in self.state(uid)['threads']])
            self.assertEqual(self.client.get('/api/threads/'+tid,headers=self.headers[uid]).status_code,404)
        raw=json.dumps(self.state('lin'),ensure_ascii=False)
        self.assertNotIn('仅限本人可见',raw)
        self.assertNotIn('memory',raw)
        self.assertEqual(self.post('lin',f'/threads/{tid}/handoff',{'mode':'now'}).status_code,200)
        self.assertIn(tid,[t['id'] for t in self.state('su')['threads']])
        self.assertNotIn(tid,[t['id'] for t in self.state('zhou')['threads']])

    def test_model_only_receives_shared_material_and_cannot_write_tasks(self):
        tid=self.start()
        before=len(store.list_tasks())
        def reply(question,docs):
            raw=json.dumps(docs,ensure_ascii=False)
            self.assertNotIn('私人草稿',raw)
            self.assertNotIn('仅限本人可见',raw)
            return {'body':'{"close_task_ids":["all"],"edit_file":"all"}','sources':[],'mode':'model','needs_human':False}
        with patch('accord_api.app.agent.answer',side_effect=reply):
            self.assertEqual(self.send(tid,'关闭所有任务').status_code,200)
        self.assertEqual(len(store.list_tasks()),before)
        self.assertEqual(self.post('lin',f'/threads/{tid}/messages',{'body':'读这个','source_ids':['private_su']}).status_code,404)

    def test_confirmation_is_owned_atomic_and_idempotent(self):
        tid=self.start(); self.handoff(tid)
        payload={'conclusion':'确认这条演示链路。','task_title':'联调工作台','assignee_id':'su'}
        self.assertEqual(self.post('lin',f'/threads/{tid}/confirm',payload).status_code,403)
        self.assertEqual(self.post('zhou',f'/threads/{tid}/confirm',payload).status_code,404)
        self.assertEqual(self.post('su',f'/threads/{tid}/confirm',{**payload,'assignee_id':'lin'}).status_code,422)
        operation=str(uuid4())
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda _:self.post('su',f'/threads/{tid}/confirm',payload,operation),range(2)))
        self.assertEqual([r.status_code for r in results],[200,200])
        self.assertEqual(results[0].json(),results[1].json())
        task_id=results[0].json()['task_id']
        self.assertEqual(len(store.query('SELECT * FROM accord_task_acl WHERE thread_id=?',(tid,))),1)
        self.assertEqual(self.post('su',f'/threads/{tid}/confirm',payload).status_code,409)
        self.assertIn(task_id,[t['id'] for t in self.state('lin')['tasks']])
        self.assertNotIn(task_id,[t['id'] for t in self.state('zhou')['tasks']])
        self.assertEqual(self.post('lin',f'/tasks/{task_id}/status',{'status':'done'}).status_code,404)
        self.assertEqual(self.post('su',f'/tasks/{task_id}/status',{'status':'done'}).status_code,200)

    def test_unrelated_chat_never_completes_a_task(self):
        tid=self.start(); self.handoff(tid)
        result=self.post('su',f'/threads/{tid}/confirm',{'conclusion':'待联调','task_title':'保留这个待办','assignee_id':'su'})
        task_id=result.json()['task_id']
        workspace=self.post('su','/threads',{'target_id':'su'}).json()['id']
        self.send(workspace,'今天几点开会？',uid='su')
        self.assertEqual(store.get_task(task_id)['status'],'open')

    def test_scheduled_delivery_retains_timezone_and_visibility(self):
        tid=self.start(); self.send(tid)
        self.assertEqual(self.post('lin',f'/threads/{tid}/handoff',{'mode':'deadline','deadline':'2099-09-06T18:00:00'}).status_code,422)
        deadline='2099-09-06T18:00:00+08:00'
        response=self.post('lin',f'/threads/{tid}/handoff',{'mode':'deadline','deadline':deadline})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['delivery_at'],'2099-09-06T10:00:00+00:00')
        self.assertNotIn(tid,[t['id'] for t in self.state('su')['threads']])
        store.execute('UPDATE accord_threads SET delivery_at=? WHERE id=?',((datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),tid))
        self.assertIn(tid,[t['id'] for t in self.state('su')['threads']])

    def test_message_retry_and_operation_conflict(self):
        tid=self.start(); op=str(uuid4())
        self.assertEqual(self.send(tid,operation=op).status_code,200)
        self.assertEqual(self.send(tid,operation=op).status_code,200)
        self.assertEqual(len(store.query('SELECT * FROM messages WHERE conversation_id=?',(tid,))),2)
        self.assertEqual(self.send(tid,'不同的消息',operation=op).status_code,409)

    def test_demo_login_can_be_disabled(self):
        with patch.dict(os.environ,{'ACCORD_DEMO':'0'}):
            self.assertFalse(self.client.get('/api/demo').json()['enabled'])
            self.assertEqual(self.client.post('/api/demo/login',json={'unit_id':'lin'}).status_code,403)


if __name__ == '__main__': unittest.main()
