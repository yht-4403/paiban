from accord_api.jobs import generation as generation_jobs
from accord_api.modules.collaboration import repository as collaboration_repository
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
from accord_api.modules.agent_runs import generation as agent
from accord_api.modules.identity import service as auth
from accord_api.modules.agent_runs import service as runtime
from accord_api.platform.db import database as store


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
        self.mock = patch('accord_api.modules.agent_runs.service.agent.stream_answer', side_effect=reply).start()
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
        tid=self.start(); before=len(collaboration_repository.list_tasks())
        self.send(tid,'先记住本轮讨论的是布局')
        self.send(tid,'按照刚才的讨论列出下一步')
        args=self.mock.call_args.args
        self.assertEqual(args[0],'按照刚才的讨论列出下一步')
        self.assertEqual([item['role'] for item in args[2]],['user','assistant'])
        self.assertIn('布局',args[2][0]['content'])
        self.assertNotIn('私人',json.dumps(args[1],ensure_ascii=False))
        self.assertEqual(len(collaboration_repository.list_tasks()),before)
        self.assertEqual(self.post('lin',f'/threads/{tid}/messages',{'body':'读这个','source_ids':['private_su']}).status_code,404)

    def test_open_chat_new_item_is_fresh_after_answer_and_deduplicates_blank_or_active(self):
        target_id = 'member_open_' + uuid4().hex[:12]
        with store.lock, store.connection() as db:
            now = store.now()
            db.execute(
                'INSERT INTO units(id,person_name,agent_name,created_at) VALUES(?,?,?,?)',
                (target_id, '新会话目标', '新会话目标的 Agent', now),
            )
            db.execute(
                'INSERT INTO accord_accounts VALUES(?,?,?,?,?)',
                (target_id, f'{target_id}@example.test', auth.FIXED_PASSWORD_HASH, 'member', now),
            )

        def open_new():
            return self.post('lin', '/chats/open', {'target_id': target_id, 'new_item': True})

        first = open_new().json()['id']
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            blank_clicks = list(pool.map(lambda _: open_new(), range(4)))
        self.assertTrue(all(response.status_code == 200 for response in blank_clicks))
        self.assertEqual({response.json()['id'] for response in blank_clicks}, {first})

        queued = self.send(first, '先回答这一轮', execute=False).json()['run_id']
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            active_clicks = list(pool.map(lambda _: open_new(), range(4)))
        self.assertTrue(all(response.status_code == 200 for response in active_clicks))
        self.assertEqual({response.json()['id'] for response in active_clicks}, {first})

        runtime.execute_run(queued)
        second = open_new().json()['id']
        self.assertNotEqual(second, first)
        self.assertEqual(
            store.query_one(
                'SELECT count(*) AS count FROM messages WHERE conversation_id=?', (second,)
            )['count'],
            0,
        )
        reopened = self.post('lin', '/chats/open', {'target_id': target_id}).json()['id']
        self.assertEqual(reopened, second)
        self.assertEqual(open_new().json()['id'], second)
        self.assertEqual(
            store.query_one(
                'SELECT count(*) AS count FROM accord_threads WHERE owner_id=? AND target_id=?',
                (self.ids['lin'], target_id),
            )['count'],
            2,
        )

    def test_process_attachment_stays_in_workbench_until_explicit_publish(self):
        from accord_api.modules.knowledge import retrieval

        tid=self.start('lin','lin')
        before={item['id'] for item in self.state('lin')['documents']}
        sent=self.post('lin',f'/threads/{tid}/attachment-messages',{
            'body':'读取附件并告诉我结论',
            'attachments':[{'filename':'阶段结论.md','content':'内部阶段结论：导航已经收拢。','mime_type':'text/markdown'}],
        })
        self.assertEqual(sent.status_code,200,sent.text)
        attachment=store.query_one('SELECT * FROM accord_thread_attachments WHERE thread_id=?',(tid,))
        self.assertIsNotNone(attachment)
        self.assertEqual({item['id'] for item in self.state('lin')['documents']},before)
        view=self.clients['lin'].get('/api/threads/'+tid).json()
        self.assertEqual(view['attachments'][0]['filename'],'阶段结论.md')
        self.assertNotIn('内部阶段结论',json.dumps(view,ensure_ascii=False))
        with store.lock:
            self.assertEqual(retrieval.search(store.connection(),self.ids['lin'],[self.ids['su']],'导航已经收拢')['sources'],[])
        runtime.execute_run(sent.json()['run_id'])
        self.assertEqual(self.mock.call_args.kwargs['attachments'][0]['content'],'内部阶段结论：导航已经收拢。')

        follow=self.send(tid,'继续依据刚才的附件回答',execute=False)
        runtime.execute_run(follow.json()['run_id'])
        self.assertEqual(self.mock.call_args.kwargs['attachments'][0]['filename'],'阶段结论.md')
        self.assertEqual(self.post('su',f"/attachments/{attachment['id']}/publish").status_code,404)
        operation=str(uuid4())
        published=self.post('lin',f"/attachments/{attachment['id']}/publish",operation=operation)
        self.assertEqual(published.status_code,200,published.text)
        self.assertEqual(self.post('lin',f"/attachments/{attachment['id']}/publish",operation=operation).json(),published.json())
        resource_id=published.json()['resource_id']
        self.assertIn(resource_id,{item['id'] for item in self.state('su')['documents']})
        self.assertEqual(self.clients['su'].get('/api/resources/'+resource_id).json()['body'],'内部阶段结论：导航已经收拢。')
        with store.lock:
            self.assertTrue(retrieval.search(store.connection(),self.ids['lin'],[self.ids['su']],'导航已经收拢')['sources'])

        peer=self.start('lin','su')
        peer_message=self.post('lin',f'/threads/{peer}/attachment-messages',{
            'body':'请结合附件回答',
            'attachments':[{'filename':'接口清单.txt','content':'待确认接口：会议回执','mime_type':'text/plain'}],
        })
        self.assertEqual(peer_message.status_code,200,peer_message.text)
        runtime.execute_run(peer_message.json()['run_id'])
        peer_attachment=store.query_one('SELECT * FROM accord_thread_attachments WHERE thread_id=?',(peer,))
        self.assertEqual(self.clients['su'].get('/api/threads/'+peer).status_code,404)
        self.post('lin',f'/threads/{peer}/handoff',{'mode':'now'})
        target_view=self.clients['su'].get('/api/threads/'+peer).json()
        self.assertEqual(target_view['attachments'][0]['filename'],'接口清单.txt')
        self.assertEqual(target_view['attachments'][0]['owner_id'],self.ids['lin'])
        self.assertNotIn('待确认接口',json.dumps(target_view,ensure_ascii=False))
        self.assertEqual(self.post('su',f"/attachments/{peer_attachment['id']}/publish").status_code,404)

        image='data:image/png;base64,aGVsbG8='
        binary=self.post('lin',f'/threads/{peer}/attachment-messages',{
            'attachments':[{'filename':'界面截图.png','content':image,'mime_type':'image/png'}],
        })
        self.assertEqual(binary.status_code,200,binary.text)
        self.assertIsNone(binary.json()['run_id'])
        image_row=store.query_one(
            "SELECT * FROM accord_thread_attachments WHERE thread_id=? AND filename='界面截图.png'",
            (peer,),
        )
        self.assertEqual(image_row['size'],5)
        self.assertEqual(self.clients['lin'].get(f"/api/attachments/{image_row['id']}").json()['content'],image)
        self.assertEqual(self.clients['su'].get(f"/api/attachments/{image_row['id']}").status_code,200)
        self.assertEqual(self.clients['zhou'].get(f"/api/attachments/{image_row['id']}").status_code,404)
        self.assertEqual(self.post('lin',f"/attachments/{image_row['id']}/publish").status_code,422)

        group=self.post('lin','/groups',{'member_ids':[self.ids['su'],self.ids['zhou']]}).json()['id']
        group_file=self.post('su',f'/groups/{group}/messages',{
            'attachments':[{'filename':'会议附件.pdf','content':'data:application/pdf;base64,JVBERi0=','mime_type':'application/pdf'}],
        })
        self.assertEqual(group_file.status_code,200,group_file.text)
        group_view=self.clients['zhou'].get('/api/threads/'+group).json()
        self.assertEqual(group_view['attachments'][0]['filename'],'会议附件.pdf')
        self.assertEqual(self.clients['lin'].get(f"/api/attachments/{group_view['attachments'][0]['id']}").status_code,200)

    def test_handoff_brief_uses_the_finished_agent_exchange(self):
        tid=self.start()
        self.send(tid,'路演主线是否已经确定？')
        result=self.post('lin',f'/threads/{tid}/handoff',{'mode':'now','note':'请本人拍板最终措辞'})
        self.assertEqual(result.status_code,200,result.text)
        brief=self.clients['su'].get('/api/threads/'+tid).json()['thread']['handoff_note']
        self.assertIn('需要处理：路演主线是否已经确定？',brief)
        self.assertIn('Agent 已整理：',brief)
        self.assertIn('发起人补充：请本人拍板最终措辞',brief)

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

        operation=str(uuid4())
        self.assertEqual(self.post('lin',f'/tasks/{task_id}/delete',operation=operation).status_code,404)
        deleted=self.post('su',f'/tasks/{task_id}/delete',operation=operation)
        self.assertEqual(deleted.status_code,200,deleted.text)
        self.assertEqual(deleted.json(),{'deleted':True})
        self.assertEqual(self.post('su',f'/tasks/{task_id}/delete',operation=operation).json(),{'deleted':True})
        self.assertNotIn(task_id,[t['id'] for t in self.state('lin')['tasks']])
        self.assertNotIn(task_id,[t['id'] for t in self.state('su')['tasks']])
        self.assertFalse(store.query_one('SELECT 1 FROM accord_task_acl WHERE task_id=?',(task_id,)))
        self.assertEqual(self.post('su',f'/tasks/{task_id}/delete').status_code,404)

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
        self.assertEqual(collaboration_repository.get_task(task_id)['status'],'open')
        self.assertEqual(len(store.query('SELECT * FROM accord_task_acl WHERE thread_id=?',(tid,))),1)
        self.assertEqual(self.post('su',f'/threads/{tid}/confirm',payload).status_code,409)
        self.assertEqual(self.send(tid,'越权消息',uid='zhou').status_code,404)
        self.assertEqual(self.clients['zhou'].get(f'/api/threads/{tid}').status_code,404)

    def test_unrelated_chat_never_completes_a_task(self):
        tid=self.start();self.handoff(tid)
        result=self.post('su',f'/threads/{tid}/confirm',{'conclusion':'待联调','task_title':'保留待办','assignee_id':self.ids['su']})
        task_id=result.json()['task_id']
        workspace=self.start('su','su');self.send(workspace,'帮我分析这个问题',uid='su')
        self.assertEqual(collaboration_repository.get_task(task_id)['status'],'open')

    def test_background_delivers_without_any_page_read(self):
        tid=self.start();self.send(tid)
        self.assertEqual(self.post('lin',f'/threads/{tid}/handoff',{'mode':'deadline','deadline':'2099-09-06T18:00:00'}).status_code,422)
        result=self.post('lin',f'/threads/{tid}/handoff',{'mode':'deadline','deadline':'2099-09-06T18:00:00+08:00'})
        self.assertEqual(result.json()['delivery_at'],'2099-09-06T10:00:00+00:00')
        self.assertNotIn(tid,[t['id'] for t in self.state('su')['threads']])
        store.execute('UPDATE accord_threads SET delivery_at=? WHERE id=?',((datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),tid))
        stop=threading.Event();worker=threading.Thread(target=generation_jobs.worker_loop,args=(stop,));worker.start()
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
        self.assertEqual(self.post('lin',f'/threads/{tid}/handoff').status_code,409)
        self.assertEqual(self.clients['su'].get('/api/threads/'+tid).status_code,404)
        runtime.execute_run(rid);self.assertEqual(self.mock.call_count,0)
        result=self.post('lin',f'/runs/{rid}/retry').json()
        runtime.execute_run(result['run_id']);self.assertEqual(self.mock.call_count,1)
        self.assertEqual(self.post('lin',f'/runs/{rid}/retry').status_code,409)
        self.assertEqual(len(store.query('SELECT * FROM messages WHERE conversation_id=?',(tid,))),2)

    def test_handoff_rejects_failed_truncated_or_empty_answers(self):
        for outcome in ('error', 'cancelled', 'length', 'empty'):
            with self.subTest(outcome=outcome):
                tid=self.start();rid=self.send(tid,execute=False).json()['run_id']
                def incomplete(question, docs, history, target_name, peer, on_delta, cancelled, **kwargs):
                    on_delta('尚未回答完整', [])
                    if outcome in ('error', 'cancelled'):
                        raise agent.ModelError('cancelled' if outcome=='cancelled' else 'network', '验收中断')
                    return {'body':'尚未回答完整' if outcome=='length' else '', 'sources':[], 'model':'test-provider',
                            'usage':{}, 'finish_reason':'length' if outcome=='length' else 'stop', 'duration_ms':1}
                self.mock.side_effect=incomplete
                runtime.execute_run(rid)
                response=self.post('lin',f'/threads/{tid}/handoff')
                self.assertEqual(response.status_code,409,response.text)
                self.assertIn('尚未完整回答',response.json()['detail'])
                self.assertEqual(self.clients['su'].get('/api/threads/'+tid).status_code,404)
                self.assertEqual(store.query_one('SELECT status FROM accord_threads WHERE id=?',(tid,))['status'],'agent')

    def test_complete_answer_unlocks_only_its_work_item(self):
        first=self.start();self.send(first)
        second=self.start();rid=self.send(second,execute=False).json()['run_id']
        self.post('lin',f'/runs/{rid}/stop')
        self.assertEqual(self.post('lin',f'/threads/{second}/handoff').status_code,409)
        self.assertEqual(self.post('lin',f'/threads/{first}/handoff').status_code,200)
        retry=self.post('lin',f'/runs/{rid}/retry').json()['run_id']
        def unknown(question, docs, history, target_name, peer, on_delta, cancelled, **kwargs):
            body='现有资料没有答案，我不知道。'
            on_delta(body, [])
            return {'body':body,'sources':[],'model':'test-provider','usage':{},'finish_reason':'stop','duration_ms':1}
        self.mock.side_effect=unknown
        runtime.execute_run(retry)
        self.assertEqual(self.post('lin',f'/threads/{second}/handoff').status_code,200)
        self.assertEqual(self.clients['su'].get('/api/threads/'+second).status_code,200)

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
            async with generation_jobs.lifespan(app):
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
        with patch.dict(os.environ,{'ACCORD_LLM_API_KEY':'test-key','ACCORD_LLM_BASE_URL':'https://provider.example/v1','ACCORD_LLM_MODEL':'test-model','ACCORD_LLM_ENABLE_THINKING':'false'}),patch('accord_api.platform.ai.provider.httpx.Client',return_value=client):
            result=agent.stream_answer('问题',[],[],'本人',False,lambda text,sources:updates.append(text),lambda:False)
        self.assertEqual(result['body'],'真实回答');self.assertEqual(result['usage']['total_tokens'],22)
        self.assertEqual(updates,['真实','真实回答']);self.assertTrue(payloads[0]['stream']);self.assertFalse(payloads[0]['enable_thinking'])


if __name__=='__main__':unittest.main()
