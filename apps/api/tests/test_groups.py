from accord_api.modules.identity import repository as identity_repository
import json
import unittest
from uuid import uuid4
from unittest.mock import patch
from fastapi.testclient import TestClient
import test_collaboration as fixtures  # Set the isolated data directory before creating the app.
from accord_api.app import app
from accord_api.modules import knowledge as context
from accord_api.modules.agent_runs import service as runtime
from accord_api.platform.db import database as store
import test_workflows as workflows


class GroupTests(unittest.TestCase):
    post = workflows.WorkflowTests.post
    get = workflows.WorkflowTests.get

    @classmethod
    def setUpClass(cls):
        if not hasattr(fixtures.CollaborationTests, 'ids'):
            fixtures.CollaborationTests.setUpClass()
        cls.clients, cls.ids = dict(fixtures.CollaborationTests.clients), dict(fixtures.CollaborationTests.ids)
        cls.clients['outside'] = TestClient(app)
        invite = cls.clients['lin'].post('/api/auth/invite', json={}).json()['code']
        response = cls.clients['outside'].post('/api/auth/register', json={'name':'群外验收成员', 'email':'groups@example.test', 'password':'test-only-groups-12345', 'invite':invite})
        assert response.status_code == 200
        cls.ids['outside'] = response.json()['me']

    def group(self):
        return self.post('lin', '/groups', {'member_ids':[self.ids['su'], self.ids['zhou']]})['id']

    def test_real_membership_messages_and_idempotent_creation(self):
        operation = str(uuid4())
        body = {'member_ids':[self.ids['su'],self.ids['zhou']]}
        tid = self.post('lin','/groups',body,operation=operation)['id']
        self.assertEqual(self.post('lin','/groups',body,operation=operation)['id'], tid)
        before = len(self.get('su','/state')['tasks'])
        for who in ('lin','su','zhou'):
            response = self.post(who, f'/groups/{tid}/messages', {'body':who+' 的真实持久化消息'})
            self.assertIsNone(response['run_id'])
            self.assertIn(tid, [g['id'] for g in self.get(who,'/state')['groups']])
        self.assertEqual(len(self.get('su','/state')['tasks']), before)
        self.assertEqual(len(self.get('lin','/threads/'+tid)['messages']), 4)
        self.get('outside','/threads/'+tid,404)
        self.assertNotIn(tid,json.dumps(self.get('outside','/state')))
        self.post('outside', f'/groups/{tid}/messages', {'body':'不能发送'},status=404)
        self.post('lin',f'/threads/{tid}/messages',{'body':'旧入口不能绕过群逻辑'},status=422)
        self.post('lin',f'/groups/{tid}/messages',{'body':'未加入的 Agent','agent_id':self.ids['outside']},status=404)

    def test_new_member_cannot_read_or_prompt_from_old_history(self):
        tid = self.group()
        self.post('lin',f'/groups/{tid}/messages',{'body':'OLD-GROUP-HISTORY'})
        self.post('su',f'/groups/{tid}/members',{'member_ids':[self.ids['outside']]},status=403)
        self.post('lin',f'/groups/{tid}/members',{'member_ids':[self.ids['outside']]})
        self.post('outside',f'/groups/{tid}/messages',{'body':'NEW-GROUP-MESSAGE'})
        visible = self.get('outside','/threads/'+tid)
        self.assertNotIn('OLD-GROUP-HISTORY',json.dumps(visible))
        self.assertIn('NEW-GROUP-MESSAGE',json.dumps(visible))
        self.assertIn('OLD-GROUP-HISTORY',json.dumps(self.get('lin','/threads/'+tid)))
        result = self.post('lin',f'/groups/{tid}/messages',{'body':'请回答新群问题','agent_id':self.ids['su']})
        snapshot = json.loads(store.query_one('SELECT manifest FROM accord_run_inputs WHERE run_id=?',(result['run_id'],))['manifest'])
        with store.lock:
            self.assertNotIn('OLD-GROUP-HISTORY',json.dumps(context.history(store.connection(),snapshot)))
        with patch('accord_api.modules.agent_runs.service.agent.stream_answer',side_effect=fixtures.reply) as call:
            runtime.execute_run(result['run_id'])
            self.assertEqual(call.call_args.args[3],identity_repository.get_unit(self.ids['su'])['person_name'])
            self.assertTrue(call.call_args.args[4])
        answer=self.get('outside','/threads/'+tid)['messages'][-1]
        self.assertEqual(answer['from_unit'],self.ids['su'])
        self.assertEqual(answer['meta']['status'],'done')
        self.assertEqual(answer['meta']['actor_id'],self.ids['lin'])

    def test_agent_reads_only_group_visible_resources_and_membership_freezes_runs(self):
        tid = self.group()
        private=self.post('lin','/resources',{'title':'个人文件','body':'PRIVATE-NEVER-GROUP','scope':'private'})['id']
        shared=self.post('lin','/resources',{'title':'公开工作资料','body':'GROUP-SHARED-EVIDENCE','scope':'team'})['id']
        self.post('lin',f'/groups/{tid}/messages',{'body':'越权引用','source_ids':[private]},status=403)
        run=self.post('lin',f'/groups/{tid}/messages',{'body':'查共享资料','agent_id':self.ids['su']})['run_id']
        snapshot=json.loads(store.query_one('SELECT manifest FROM accord_run_inputs WHERE run_id=?',(run,))['manifest'])
        tool=context.ToolContext(run,snapshot)
        self.assertNotIn(private,[r['id'] for r in snapshot['resources']])
        self.assertEqual(tool.execute('read','context_read',{'resource_id':shared})['content'],'GROUP-SHARED-EVIDENCE')
        self.post('su','/runs/'+run+'/stop',status=404)
        self.post('lin',f'/groups/{tid}/members',{'member_ids':[self.ids['outside']]},status=409)
        self.post('lin','/runs/'+run+'/stop')
        self.post('lin',f'/groups/{tid}/members',{'member_ids':[self.ids['outside']]})
        self.post('lin','/runs/'+run+'/retry',status=409)

    def test_rename_requires_owner_and_persists(self):
        tid=self.group()
        self.post('su',f'/groups/{tid}/rename',{'title':'不能改'},status=403)
        self.post('lin',f'/groups/{tid}/rename',{'title':'联合验收'})
        self.assertEqual(self.get('zhou','/threads/'+tid)['thread']['title'],'联合验收')
