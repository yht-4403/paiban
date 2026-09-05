import json
import unittest
from uuid import uuid4
from accord_api.platform.errors import DomainError
import test_workflows as workflows
import test_collaboration as fixtures
from accord_api.modules import knowledge as context
from accord_api.platform.db import database as store


class OpenMemoryTests(unittest.TestCase):
    post = workflows.WorkflowTests.post
    get = workflows.WorkflowTests.get
    send = workflows.WorkflowTests.send
    resource = workflows.WorkflowTests.resource
    thread = workflows.WorkflowTests.thread

    @classmethod
    def setUpClass(cls):
        if not hasattr(fixtures.CollaborationTests, 'ids'):
            fixtures.CollaborationTests.setUpClass()
        cls.clients, cls.ids = fixtures.CollaborationTests.clients, fixtures.CollaborationTests.ids

    def tools(self, tid):
        run = self.send('lin', tid, execute=False)
        self.addCleanup(lambda: self.post('lin', f'/runs/{run}/stop'))
        snapshot = json.loads(store.query_one('SELECT manifest FROM accord_run_inputs WHERE run_id=?', (run,))['manifest'])
        return context.ToolContext(run, snapshot)

    def test_automatic_search_uses_authorized_sources_without_preloading_bodies(self):
        marker = 'evidence' + uuid4().hex
        own = self.resource(body=marker)
        other = self.post('su', '/resources', {'title':'不应出现在目录', 'body':marker, 'scope':'private'})['id']
        tool = self.tools(self.thread())
        self.assertEqual(tool.documents(), [])
        catalog = tool.execute('list', 'context_list', {})
        self.assertIn(own, json.dumps(catalog)); self.assertNotIn(other, json.dumps(catalog))
        self.assertNotIn(marker, json.dumps(catalog))
        result = tool.execute('search', 'context_search', {'query':marker})
        self.assertEqual([r['id'] for r in result['results']], [own])
        self.assertIn('error', tool.execute('denied', 'context_read', {'resource_id':other}))

    def test_peer_automatic_scope_excludes_private_and_rechecks_shared_revocation(self):
        private = self.resource()
        shared = self.resource(scope='team', body='共同可见的项目进度')
        tool = self.tools(self.thread(peer=True))
        ids = [r['id'] for r in tool.manifest['resources']]
        self.assertIn(shared, ids); self.assertNotIn(private, ids)
        self.post('lin', '/resources/'+shared+'/update', {'expected_version':1, 'title':'已收回', 'body':'现在私有', 'scope':'private'})
        with self.assertRaises(DomainError):
            tool.execute('revoked', 'context_read', {'resource_id':shared})

    def test_automatic_run_pins_versions_and_respects_exclusion(self):
        source, excluded = self.resource(body='第一版'), self.resource(body='不要读')
        tid = self.thread()
        self.post('lin', f'/threads/{tid}/bindings', {'expected_version':0, 'excluded':[excluded]})
        tool = self.tools(tid)
        self.post('lin', '/resources/'+source+'/update', {'expected_version':1,'title':'更新','body':'第二版','scope':'private'})
        self.assertEqual(tool.execute('pinned', 'context_read', {'resource_id':source})['content'], '第一版')
        self.assertNotIn(excluded, [r['id'] for r in tool.manifest['resources']])

    def test_personal_chat_can_be_removed_restored_but_peer_and_foreign_cannot(self):
        tid = self.thread()
        operation = str(uuid4())
        self.post('lin', f'/threads/{tid}/archive', {'archived':True}, operation=operation)
        self.post('lin', f'/threads/{tid}/archive', {'archived':True}, operation=operation)
        state = self.get('lin','/state')
        self.assertNotIn(tid, [t['id'] for t in state['threads']])
        self.assertEqual([t['id'] for t in state['archived_threads']].count(tid), 1)
        self.post('su', f'/threads/{tid}/archive', {'archived':False}, status=404)
        self.post('lin', f'/threads/{tid}/archive', {'archived':False})
        self.assertIn(tid, [t['id'] for t in self.get('lin','/state')['threads']])
        peer = self.thread(peer=True)
        self.post('lin', f'/threads/{peer}/archive', {'archived':True}, status=403)
        run = self.send('lin', tid, execute=False)
        try:
            self.post('lin', f'/threads/{tid}/archive', {'archived':True}, status=409)
        finally:
            self.post('lin', f'/runs/{run}/stop')
