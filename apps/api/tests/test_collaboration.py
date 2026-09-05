import asyncio
import concurrent.futures
import json
import os
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import patch

_temporary = tempfile.TemporaryDirectory(prefix='accord-test-')
os.environ['ACCORD_DATA_DIR'] = _temporary.name
from fastapi.testclient import TestClient
from accord_api.app import app
from accord_api import agent, auth, runtime, store


def reply(question, docs, history, target_name, peer, on_delta, cancelled, **kwargs):
    body = '## 已整理\n\n' + question
    on_delta(body, [d['id'] for d in docs])
    return {'body':body, 'sources':[d['id'] for d in docs], 'model':'test-provider',
            'usage':{'prompt_tokens':20,'completion_tokens':10,'total_tokens':30}, 'finish_reason':'stop','duration_ms':12}


class CollaborationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clients = {alias:TestClient(app) for alias in ('lin','su','zhou')}
        cls.ids = {}
        cls.password = 'test-only-password-12345'
        first=cls.clients['lin'].post('/api/auth/setup',json={'name':'测试甲','email':'a@example.test','password':cls.password,'workspace':'隔离验收工作空间'})
        assert first.status_code == 200, first.text
        cls.ids['lin']=first.json()['me']
        initial=cls.clients['lin'].get('/api/state').json()
        assert initial['documents']==[] and initial['threads']==[] and initial['tasks']==[]
        for alias,email,name in [('su','b@example.test','测试乙'),('zhou','c@example.test','测试丙')]:
            code=cls.clients['lin'].post('/api/auth/invite',json={}).json()['code']
            result=cls.clients[alias].post('/api/auth/register',json={'name':name,'email':email,'password':cls.password,'invite':code})
            assert result.status_code==200, result.text
            cls.ids[alias]=result.json()['me']
        cls.doc=cls.clients['lin'].post('/api/documents',json={'title':'工作台资料','body':'工作台采用 Tutti UI System。','operation_id':str(uuid4())}).json()['id']
        store.execute('INSERT INTO memories(id,unit_id,title,body,source,created_at) VALUES(?,?,?,?,?,?)',('private_su',cls.ids['su'],'私人草稿','仅限本人可见','test',store.now()))

    def setUp(self):
        self.mock = patch('accord_api.runtime.agent.stream_answer', side_effect=reply).start()
        self.addCleanup(patch.stopall)

    def post(self, uid, path, body=None, operation=None):
        return self.clients[uid].post('/api'+path,json={**(body or {}),'operation_id':operation or str(uuid4())})

    def state(self,uid):
        return self.clients[uid].get('/api/state').json()

    def start(self, owner='lin', target='su'):
        response=self.post(owner,'/threads',{'target_id':self.ids[target]})
        self.assertEqual(response.status_code,200)
        return response.json()['id']

    def send(self,tid,body='工作台用什么 UI？',uid='lin',operation=None,execute=True):
        response=self.post(uid,f'/threads/{tid}/messages',{'body':body},operation)
        if response.status_code==200 and execute and response.json().get('run_id'):
            runtime.execute_run(response.json()['run_id'])
        return response

    def handoff(self,tid):
        self.assertEqual(self.send(tid).status_code,200)
        self.assertEqual(self.post('lin',f'/threads/{tid}/handoff',{'mode':'now','note':'需要本人确认'}).status_code,200)

    def test_anonymous_and_identity_switch_routes_are_closed(self):
        client=TestClient(app)
        self.assertEqual(client.get('/api/state').status_code,401)
        for path in ['/api/demo','/api/demo/login','/api/snapshot','/api/decisions/any/close','/ws']:
            self.assertEqual(client.get(path).status_code,404)
        self.assertNotIn('演示',json.dumps(self.state('lin'),ensure_ascii=False))

    def test_agent_channel_private_until_explicit_handoff(self):
        tid=self.start();self.send(tid)
        for uid in ('su','zhou'):
            self.assertNotIn(tid,[t['id'] for t in self.state(uid)['threads']])
            self.assertEqual(self.clients[uid].get('/api/threads/'+tid).status_code,404)
        raw=json.dumps(self.state('lin'),ensure_ascii=False)
        self.assertNotIn('仅限本人可见',raw);self.assertNotIn('password',raw)
        self.assertEqual(self.post('lin',f'/threads/{tid}/handoff',{'mode':'now'}).status_code,200)
        self.assertIn(tid,[t['id'] for t in self.state('su')['threads']])
        self.assertNotIn(tid,[t['id'] for t in self.state('zhou')['threads']])

    def test_model_receives_history_and_shared_material_only(self):
        tid=self.start(); before=len(store.list_tasks())
        self.send(tid,'先记住本轮讨论的是布局')
        self.send(tid,'按照刚才的讨论列出下一步')
        args=self.mock.call_args.args
        self.assertEqual(args[0],'按照刚才的讨论列出下一步')
        self.assertEqual([item['role'] for item in args[2]],['user','assistant'])
        self.assertIn('布局',args[2][0]['content'])
        self.assertNotIn('私人',json.dumps(args[1],ensure_ascii=False))
        self.assertEqual(len(store.list_tasks()),before)
        self.assertEqual(self.post('lin',f'/threads/{tid}/messages',{'body':'读这个','source_ids':['private_su']}).status_code,404)

    def test_confirmation_owned_atomic_and_idempotent(self):
        tid=self.start();self.handoff(tid)
        payload={'conclusion':'确认安排','task_title':'联调工作台','assignee_id':self.ids['su']}
        self.assertEqual(self.post('lin',f'/threads/{tid}/confirm',payload).status_code,403)
        self.assertEqual(self.post('zhou',f'/threads/{tid}/confirm',payload).status_code,404)
        self.assertEqual(self.post('su',f'/threads/{tid}/confirm',{**payload,'assignee_id':self.ids['lin']}).status_code,422)
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

    def test_confirmed_conversation_continues_without_new_agent_or_task(self):
        tid=self.start();self.handoff(tid)
        self.assertEqual(self.send(tid,'我来确认',uid='su').status_code,200)
        payload={'conclusion':'我负责联调','task_title':'继续跟进联调','assignee_id':self.ids['su']}
        accepted=self.post('su',f'/threads/{tid}/confirm',payload)
        self.assertEqual(accepted.status_code,200)
        task_id=accepted.json()['task_id']
        calls=self.mock.call_count
        for uid,body in [('lin','补充一个边界条件'),('su','收到，继续在这里同步')]:
            result=self.send(tid,body,uid=uid)
            self.assertEqual(result.status_code,200)
            self.assertIsNone(result.json()['run_id'])
        self.assertEqual(self.mock.call_count,calls)
        view=self.clients['su'].get(f'/api/threads/{tid}').json()
        self.assertEqual(view['thread']['status'],'resolved')
        self.assertEqual(view['thread']['id'],tid)
        self.assertEqual(sum(m['body']=='本人开始回复，Agent 暂停代答。' for m in view['messages']),1)
        self.assertEqual(store.get_task(task_id)['status'],'open')
        self.assertEqual(len(store.query('SELECT * FROM accord_task_acl WHERE thread_id=?',(tid,))),1)
        self.assertEqual(self.post('su',f'/threads/{tid}/confirm',payload).status_code,409)
        self.assertEqual(self.send(tid,'越权消息',uid='zhou').status_code,404)
        self.assertEqual(self.clients['zhou'].get(f'/api/threads/{tid}').status_code,404)

    def test_unrelated_chat_never_completes_a_task(self):
        tid=self.start();self.handoff(tid)
        result=self.post('su',f'/threads/{tid}/confirm',{'conclusion':'待联调','task_title':'保留待办','assignee_id':self.ids['su']})
        task_id=result.json()['task_id']
        workspace=self.start('su','su');self.send(workspace,'帮我分析这个问题',uid='su')
        self.assertEqual(store.get_task(task_id)['status'],'open')

    def test_background_delivers_without_any_page_read(self):
        tid=self.start();self.send(tid)
        self.assertEqual(self.post('lin',f'/threads/{tid}/handoff',{'mode':'deadline','deadline':'2099-09-06T18:00:00'}).status_code,422)
        result=self.post('lin',f'/threads/{tid}/handoff',{'mode':'deadline','deadline':'2099-09-06T18:00:00+08:00'})
        self.assertEqual(result.json()['delivery_at'],'2099-09-06T10:00:00+00:00')
        self.assertNotIn(tid,[t['id'] for t in self.state('su')['threads']])
        store.execute('UPDATE accord_threads SET delivery_at=? WHERE id=?',((datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),tid))
        stop=threading.Event();worker=threading.Thread(target=runtime.worker_loop,args=(stop,));worker.start()
        try:
            deadline=time.monotonic()+2
            while store.query_one('SELECT status FROM accord_threads WHERE id=?',(tid,))['status']!='waiting' and time.monotonic()<deadline: time.sleep(.02)
            self.assertEqual(store.query_one('SELECT status FROM accord_threads WHERE id=?',(tid,))['status'],'waiting')
        finally:stop.set();worker.join()

    def test_idempotency_precedes_paid_call_and_saves_user_immediately(self):
        tid=self.start();op=str(uuid4())
        first=self.send(tid,operation=op,execute=False)
        self.assertEqual(first.status_code,200)
        self.assertEqual(self.mock.call_count,0)
        messages=store.query('SELECT * FROM messages WHERE conversation_id=?',(tid,))
        self.assertEqual(len(messages),2)
        self.assertEqual(json.loads(messages[1]['meta'])['status'],'queued')
        self.assertEqual(self.send(tid,operation=op,execute=False).json(),first.json())
        self.assertEqual(self.send(tid,'不同消息',operation=op,execute=False).status_code,409)
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            list(pool.map(lambda _:runtime.execute_run(first.json()['run_id']),range(2)))
        self.assertEqual(self.mock.call_count,1)
        self.send(tid,operation=op)
        self.assertEqual(self.mock.call_count,1)
        self.assertEqual(len(store.query('SELECT * FROM messages WHERE conversation_id=?',(tid,))),2)

    def test_cancel_retry_and_run_ownership(self):
        tid=self.start(); first=self.send(tid,execute=False).json();rid=first['run_id']
        self.assertEqual(self.post('su',f'/runs/{rid}/stop').status_code,404)
        self.assertEqual(self.post('lin',f'/threads/{tid}/handoff',{}).status_code,409)
        self.assertEqual(self.post('lin',f'/runs/{rid}/stop').status_code,200)
        runtime.execute_run(rid);self.assertEqual(self.mock.call_count,0)
        result=self.post('lin',f'/runs/{rid}/retry').json()
        runtime.execute_run(result['run_id']);self.assertEqual(self.mock.call_count,1)
        self.assertEqual(self.post('lin',f'/runs/{rid}/retry').status_code,409)
        self.assertEqual(len(store.query('SELECT * FROM messages WHERE conversation_id=?',(tid,))),2)

    def test_active_run_rejects_second_message_without_orphan_records(self):
        tid=self.start();rid=self.send(tid,execute=False).json()['run_id']
        self.assertEqual(self.send(tid,'下一条',execute=False).status_code,409)
        self.assertEqual(len(store.query('SELECT * FROM messages WHERE conversation_id=?',(tid,))),2)
        runtime.execute_run(rid)

    def test_error_is_persisted_and_does_not_invent_a_response(self):
        tid=self.start();rid=self.send(tid,execute=False).json()['run_id']
        self.mock.side_effect=agent.ModelError('network','暂时无法连接模型服务，请稍后重试。')
        runtime.execute_run(rid)
        run=store.query_one('SELECT * FROM accord_runs WHERE id=?',(rid,))
        message=store.query_one('SELECT * FROM messages WHERE id=?',(run['assistant_message_id'],))
        self.assertEqual(run['status'],'error');self.assertEqual(message['body'],'')
        self.assertEqual(json.loads(message['meta'])['error_code'],'network')

    def test_login_logout_password_storage_and_invite_constraints(self):
        client=TestClient(app)
        self.assertFalse(client.get('/api/auth/status').json()['needs_setup'])
        self.assertEqual(client.post('/api/auth/setup',json={'name':'X','workspace':'X','email':'x@example.test','password':self.password}).status_code,409)
        self.assertEqual(client.post('/api/auth/register',json={'name':'X','email':'x@example.test','password':self.password,'invite':'invalid'}).status_code,400)
        self.assertEqual(client.post('/api/auth/login',json={'email':'a@example.test','password':'wrong'}).status_code,401)
        result=client.post('/api/auth/login',json={'email':'A@example.test','password':self.password})
        self.assertEqual(result.status_code,200)
        self.assertIn('HttpOnly',result.headers['set-cookie']);self.assertNotIn('token',result.json())
        encoded=store.query_one('SELECT password_hash FROM accord_accounts WHERE unit_id=?',(self.ids['lin'],))['password_hash']
        self.assertNotIn(self.password,encoded)
        self.assertEqual(self.clients['su'].post('/api/auth/invite',json={}).status_code,403)
        self.assertEqual(client.post('/api/auth/logout',json={}).status_code,200)
        self.assertEqual(client.get('/api/state').status_code,401)

    def test_cross_origin_writes_rejected(self):
        self.assertEqual(self.clients['lin'].post('/api/auth/invite',headers={'Origin':'https://unrelated.example'},json={}).status_code,403)

    def test_reasoning_preferences_are_personal_validated_and_snapshotted(self):
        with patch.dict(os.environ, {'ACCORD_LLM_PROVIDER':'deepseek', 'ACCORD_LLM_REASONING_EFFORT':'max'}):
            self.assertEqual(TestClient(app).post('/api/profile/reasoning', json={'reasoning_effort':'low','operation_id':str(uuid4())}).status_code, 401)
            self.assertEqual(self.state('lin')['model']['reasoning_effort'], 'max')
            self.assertEqual(self.post('lin', '/profile/reasoning', {'reasoning_effort':'xhigh'}).status_code, 422)
            self.assertEqual(self.post('lin', '/profile/reasoning', {'reasoning_effort':'low'}).status_code, 200)
            self.assertEqual(self.state('lin')['model']['reasoning_effort'], 'low')
            self.assertEqual(self.state('su')['model']['reasoning_effort'], 'max')
            tid = self.start('lin', 'lin')
            rid = self.send(tid, execute=False).json()['run_id']
            self.post('lin', '/profile/reasoning', {'reasoning_effort':'max'})
            runtime.execute_run(rid)
            self.assertEqual(self.mock.call_args.kwargs['reasoning_effort'], 'low')
            self.assertEqual(store.query_one('SELECT reasoning_effort FROM accord_runs WHERE id=?',(rid,))['reasoning_effort'], 'low')
            rid2 = self.send(tid, execute=False).json()['run_id']
            self.post('lin', f'/runs/{rid2}/stop')
            self.post('lin', '/profile/reasoning', {'reasoning_effort':'high'})
            retried = self.post('lin', f'/runs/{rid2}/retry').json()['run_id']
            runtime.execute_run(retried)
            self.assertEqual(self.mock.call_args.kwargs['reasoning_effort'], 'high')
            self.post('lin', '/profile/reasoning', {'reasoning_effort':'max'})

    def test_reasoning_continuity_is_internal_and_state_is_visible(self):
        with patch.dict(os.environ, {'ACCORD_LLM_PROVIDER':'deepseek'}):
            tid = self.start('lin','lin')
            def reasoning_reply(*args, **kwargs):
                kwargs['on_phase']('thinking')
                message = self.clients['lin'].get('/api/threads/'+tid).json()['messages'][-1]
                self.assertEqual(message['meta']['phase'], 'thinking')
                return {**reply(*args, **kwargs), 'reasoning_content':'INTERNAL_REASONING_ONLY'}
            self.mock.side_effect = reasoning_reply
            self.send(tid)
            self.assertNotIn('INTERNAL_REASONING_ONLY', self.clients['lin'].get('/api/threads/'+tid).text)
            self.send(tid, '接着回答')
            self.assertEqual(self.mock.call_args.args[2][-1]['reasoning_content'], 'INTERNAL_REASONING_ONLY')

    def test_restart_marks_interrupted_run_without_auto_spending(self):
        tid=self.start();rid=self.send(tid,execute=False).json()['run_id']
        store.execute("UPDATE accord_runs SET status='running' WHERE id=?",(rid,))
        async def restart():
            async with runtime.lifespan(app):
                self.assertEqual(store.query_one('SELECT status FROM accord_runs WHERE id=?',(rid,))['status'],'error')
        asyncio.run(restart())
        self.assertEqual(self.mock.call_count,0)


class ProviderTests(unittest.TestCase):
    def test_no_shared_documents_still_builds_contextual_model_request(self):
        messages,sources=agent.context_messages('接着写',[],[{'role':'user','content':'我要设计一个协作工具'},{'role':'assistant','content':'先确定目标'}],'本人',False)
        self.assertEqual(sources,[]);self.assertEqual(messages[-1]['content'],'接着写')
        self.assertEqual(messages[-3]['content'],'我要设计一个协作工具')

    def test_stream_payload_completion_and_reported_usage(self):
        import httpx
        payloads=[]
        def handler(request):
            payloads.append(json.loads(request.content))
            events=[{'choices':[{'delta':{'content':'真实'},'finish_reason':None}]},{'choices':[{'delta':{'content':'回答'},'finish_reason':'stop'}]}, {'choices':[],'usage':{'prompt_tokens':20,'completion_tokens':2,'total_tokens':22}}]
            return httpx.Response(200,content=('\n\n'.join('data: '+json.dumps(e) for e in events)+'\n\ndata: [DONE]\n\n').encode())
        client=httpx.Client(transport=httpx.MockTransport(handler))
        updates=[]
        with patch.dict(os.environ,{'ACCORD_LLM_API_KEY':'test-key','ACCORD_LLM_BASE_URL':'https://provider.example/v1','ACCORD_LLM_MODEL':'test-model','ACCORD_LLM_ENABLE_THINKING':'false'}),patch('accord_api.agent.httpx.Client',return_value=client):
            result=agent.stream_answer('问题',[],[],'本人',False,lambda text,sources:updates.append(text),lambda:False)
        self.assertEqual(result['body'],'真实回答');self.assertEqual(result['usage']['total_tokens'],22)
        self.assertEqual(updates,['真实','真实回答']);self.assertTrue(payloads[0]['stream']);self.assertFalse(payloads[0]['enable_thinking'])


if __name__=='__main__':unittest.main()
