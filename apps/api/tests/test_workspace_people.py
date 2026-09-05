import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4
from accord_api.platform.errors import DomainError
import test_workflows as workflows
import test_collaboration as fixtures
from accord_api.modules.activity import service as activity
from accord_api.modules import knowledge as context
from accord_api.modules.agent_runs import service as runtime
from accord_api.platform.db import database as store


class PeopleTests(unittest.TestCase):
    post=workflows.WorkflowTests.post
    get=workflows.WorkflowTests.get
    send=workflows.WorkflowTests.send
    @classmethod
    def setUpClass(cls):
        if not hasattr(fixtures.CollaborationTests,'ids'):fixtures.CollaborationTests.setUpClass()
        cls.clients,cls.ids=fixtures.CollaborationTests.clients,fixtures.CollaborationTests.ids

    def preferences(self,who,automatic,work_title=False):
        current=self.get(who,'/state')['activity_preferences']
        return self.post(who,'/profile/activity',{'expected_version':current['version'],'automatic':automatic,'work_title':work_title})

    def test_person_chat_reuses_existing_and_preserves_private_segments(self):
        a=self.post('lin','/threads',{'target_id':self.ids['su']})['id']
        self.send('lin',a,'A-UNSHARED-'+a)
        opened=self.post('lin','/chats/open',{'target_id':self.ids['su']})['id']
        self.assertEqual(opened,a)
        self.assertEqual(self.post('lin','/chats/open',{'target_id':self.ids['su']})['id'],a)
        b=self.post('su','/threads',{'target_id':self.ids['lin']})['id']
        self.send('su',b,'B-PRIVATE-'+b)
        self.assertNotIn('B-PRIVATE-'+b,json.dumps(self.get('lin',f'/threads/{a}?person_history=true')))
        self.get('su','/threads/'+a,404)
        self.post('lin',f'/threads/{a}/handoff')
        merged=self.get('su',f'/threads/{a}?person_history=true')
        self.assertIn('A-UNSHARED-'+a,json.dumps(merged))
        self.assertIn('B-PRIVATE-'+b,json.dumps(merged))
        self.assertNotIn('B-PRIVATE-'+b,json.dumps(self.get('lin',f'/threads/{a}?person_history=true')))
        self.get('zhou',f'/threads/{a}?person_history=true',404)

    def test_activity_is_opt_in_expires_and_never_contains_message_body(self):
        self.preferences('su',False)
        tid=self.post('su','/threads',{'target_id':self.ids['su'],'title':'OWN-SHARED-TITLE'})['id']
        self.send('su',tid,'NEVER-AUTOMATICALLY-SHARE-BODY')
        body={'client_id':uuid4().hex,'surface':'work','thread_id':tid,'active':True}
        self.assertFalse(self.post('su','/presence',body)['recorded'])
        self.assertIsNone(self.get('lin',f"/members/{self.ids['su']}/activity")['work'])
        self.preferences('su',True)
        self.assertTrue(self.post('su','/presence',body)['recorded'])
        visible=self.get('lin',f"/members/{self.ids['su']}/activity")
        self.assertEqual(visible['label'],'在 Accord 工作');self.assertIsNone(visible['work'])
        self.preferences('su',True,True)
        visible=self.get('lin',f"/members/{self.ids['su']}/activity")
        self.assertEqual(visible['work']['title'],'OWN-SHARED-TITLE')
        self.assertNotIn('NEVER-AUTOMATICALLY-SHARE-BODY',json.dumps(self.get('lin','/state')))
        store.execute('UPDATE accord_presence SET seen_at=? WHERE owner_id=?',((datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat(),self.ids['su']))
        self.assertIsNone(self.get('lin',f"/members/{self.ids['su']}/activity")['work'])
        self.preferences('su',False)

    def test_activity_cannot_disclose_a_third_persons_chat_title(self):
        self.preferences('su',True,True)
        tid=self.post('su','/threads',{'target_id':self.ids['zhou'],'title':'THIRD-PARTY-PRIVATE-TITLE'})['id']
        self.post('su','/presence',{'client_id':uuid4().hex,'surface':'chat','thread_id':tid})
        response=self.get('lin',f"/members/{self.ids['su']}/activity")
        self.assertEqual(response['label'],'在 Accord 聊天');self.assertIsNone(response['work'])
        self.assertNotIn('THIRD-PARTY-PRIVATE-TITLE',json.dumps(response))
        self.post('lin','/presence',{'client_id':uuid4().hex,'surface':'chat','thread_id':tid}) # disabled: no collection
        self.preferences('su',False)

    def test_model_status_tool_is_available_without_documents_and_rechecks_permission(self):
        self.preferences('su',True)
        folder=self.post('lin','/folders',{'name':'空范围状态查询'})['id']
        tid=self.post('lin','/threads',{'target_id':self.ids['su'],'folder_id':folder})['id']
        rid=self.send('lin',tid,execute=False)
        manifest=json.loads(store.query_one('SELECT manifest FROM accord_run_inputs WHERE run_id=?',(rid,))['manifest'])
        tool=context.ToolContext(rid,manifest)
        result=tool.execute('status-'+uuid4().hex,'colleague_status',{})
        self.assertIn('label',result);self.assertEqual(manifest['resources'],[])
        rejected=tool.execute('spoof-'+uuid4().hex,'colleague_status',{'actor_id':self.ids['zhou']})
        self.assertIn('error',rejected)
        self.preferences('su',False)
        with self.assertRaises(DomainError):tool.check()
        self.post('lin','/runs/'+rid+'/stop')

    def test_priority_and_progress_keep_task_acl(self):
        tid=self.post('lin','/threads',{'target_id':self.ids['su']})['id'];self.send('lin',tid)
        self.post('lin',f'/threads/{tid}/handoff')
        task=self.post('su',f'/threads/{tid}/confirm',{'conclusion':'确认','task_title':'PRIORITY-TASK-'+tid,'assignee_id':self.ids['su']})['task_id']
        self.post('su',f'/tasks/{task}/priority',{'priority':'high'})
        self.post('lin',f'/tasks/{task}/priority',{'priority':'low'},status=404)
        visible=self.get('lin',f"/members/{self.ids['su']}/activity")['shared_tasks']
        self.assertEqual(next(t['priority'] for t in visible if t['id']==task),'high')
        third=self.get('zhou',f"/members/{self.ids['su']}/activity")
        self.assertNotIn('PRIORITY-TASK-'+tid,json.dumps(third))
