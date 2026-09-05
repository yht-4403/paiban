import concurrent.futures
import json
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx

# Reuse the isolated accounts; this module can also be run on its own.
import test_collaboration as fixtures
from test_collaboration import reply
from accord_api import agent, context, runtime, store


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not hasattr(fixtures.CollaborationTests, 'ids'):
            fixtures.CollaborationTests.setUpClass()
        cls.clients, cls.ids = fixtures.CollaborationTests.clients, fixtures.CollaborationTests.ids

    def post(self, who, path, body=None, operation=None, status=200):
        response = self.clients[who].post('/api'+path, json={**(body or {}), 'operation_id': operation or str(uuid4())})
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    def get(self, who, path, status=200):
        response = self.clients[who].get('/api'+path)
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    def resource(self, scope='private', body='PRIVATE-CONTEXT-ONLY', title='私人研究'):
        return self.post('lin', '/resources', {'title': title, 'body': body, 'scope': scope})['id']

    def thread(self, folder='', peer=False):
        return self.post('lin', '/threads', {'target_id': self.ids['su' if peer else 'lin'], 'folder_id': folder})['id']

    def send(self, who, tid, body='根据当前资料回答', execute=True):
        result = self.post(who, f'/threads/{tid}/messages', {'body': body})
        if execute:
            with patch('accord_api.runtime.agent.stream_answer', side_effect=reply):
                runtime.execute_run(result['run_id'])
        return result['run_id']

    def topic(self):
        return self.post('lin', '/topics', {'title': '探索测试 '+uuid4().hex[:6], 'brief': '各自提出可验证的方案。', 'member_ids': [self.ids['su']]})['id']

    def submit(self, who, rid, body, version=0):
        return self.post(who, f'/topics/{rid}/submit', {'expected_version': version, 'title': body, 'body': body})

    def release(self, rid):
        current = self.get('lin', '/topics/'+rid)
        return self.post('lin', f'/topics/{rid}/release', {'expected_version': current['version']})

    def test_private_resources_never_enter_peer_or_other_accounts(self):
        resource = self.resource()
        self.get('su', '/resources/'+resource, 404)
        self.assertNotIn('PRIVATE-CONTEXT-ONLY', json.dumps(self.get('su', '/state')))
        tid = self.thread(peer=True)
        self.post('lin', f'/threads/{tid}/bindings', {'expected_version': 0, 'included': [resource]}, status=403)
        self.post('lin', f'/threads/{tid}/messages', {'body': '试读', 'source_ids': [resource]}, status=404)
        self.assertEqual(self.get('lin', '/threads/'+tid)['messages'], [])

    def test_folder_move_pins_old_run_and_uses_new_defaults_next_turn(self):
        resource = self.resource(body='PINNED-VERSION-ONE')
        a = self.post('lin', '/folders', {'name': '资料 A'})['id']
        b = self.post('lin', '/folders', {'name': '资料 B'})['id']
        self.post('lin', f'/folders/{a}/bindings', {'expected_version': 0, 'included': [resource]})
        tid = self.thread(a)
        rid = self.send('lin', tid, execute=False)
        self.post('lin', '/resources/'+resource+'/update', {'expected_version': 1, 'title': '已更新', 'body': 'VERSION-TWO', 'scope': 'private'})
        self.post('lin', f'/threads/{tid}/move', {'expected_version': 1, 'folder_id': b})
        snapshot = json.loads(store.query_one('SELECT manifest FROM accord_run_inputs WHERE run_id=?', (rid,))['manifest'])
        self.assertEqual(snapshot['resources'][0]['version'], 1)
        with patch('accord_api.runtime.agent.stream_answer', side_effect=reply) as call:
            runtime.execute_run(rid)
            self.assertEqual(call.call_args.args[1][0]['body'], 'PINNED-VERSION-ONE')
        data = self.get('lin', '/threads/'+tid)
        self.assertEqual(data['thread']['folder_id'], b)
        self.assertEqual(data['context']['resources'], [])
        rid2 = self.send('lin', tid, execute=False)
        with patch('accord_api.runtime.agent.stream_answer', side_effect=reply) as call:
            runtime.execute_run(rid2)
            self.assertEqual(call.call_args.args[1], [])
            self.assertTrue(call.call_args.args[2])
        self.post('lin', f'/threads/{tid}/move', {'expected_version': 1, 'folder_id': a}, status=409)
        self.get('su', '/threads/'+tid, 404)

    def test_empty_context_never_falls_back_to_global_documents(self):
        self.resource(scope='team', body='DO-NOT-LOAD-WITHOUT-BINDING')
        tid = self.thread(); rid = self.send('lin', tid, execute=False)
        with patch('accord_api.runtime.agent.stream_answer', side_effect=reply) as call:
            runtime.execute_run(rid)
            self.assertEqual(call.call_args.args[1], [])

    def test_mounted_folder_updates_next_turn_but_keeps_running_snapshot(self):
        first, second = self.resource(body='FIRST-FOLDER-CONTEXT'), self.resource(body='SECOND-FOLDER-CONTEXT')
        folder = self.post('lin', '/folders', {'name': '持续引用'})['id']
        self.post('lin', f'/folders/{folder}/bindings', {'expected_version': 0, 'included': [first]})
        tid = self.thread()
        self.post('lin', f'/threads/{tid}/bindings', {'expected_version': 0, 'folder_ids': [folder]})
        rid = self.send('lin', tid, execute=False)
        self.post('lin', f'/folders/{folder}/bindings', {'expected_version': 1, 'included': [second]})
        self.assertEqual([r['id'] for r in self.get('lin', f'/threads/{tid}/context')['resources']], [second])
        with patch('accord_api.runtime.agent.stream_answer', side_effect=reply) as call:
            runtime.execute_run(rid)
            self.assertEqual([r['id'] for r in call.call_args.args[1]], [first])
        self.post('lin', f'/folders/{folder}/remove', {'expected_version': 1}, status=409)
        other = self.post('su', '/threads', {'target_id': self.ids['su']})['id']
        self.post('su', f'/threads/{other}/bindings', {'expected_version': 0, 'folder_ids': [folder]}, status=404)
        self.post('lin', f'/threads/{tid}/bindings', {'expected_version': 1, 'folder_ids': []})
        self.assertEqual(self.get('lin', f'/threads/{tid}/context')['resources'], [])

    def test_nested_collection_revocation_blocks_release_and_handoff(self):
        leaf = self.resource(scope='team')
        bundle = self.post('lin', '/resources', {'title': '共享集合', 'scope': 'team', 'resource_ids': [leaf]})['id']
        rid = self.topic()
        self.post('lin', f'/topics/{rid}/submit', {'expected_version': 0, 'title': '方案', 'body': '引用集合', 'source_ids': [bundle]})
        self.post('lin', f'/resources/{leaf}/update', {'expected_version': 1, 'title': '收回引用', 'body': 'private', 'scope': 'private'})
        version = self.get('lin', '/topics/'+rid)['version']
        self.post('lin', f'/topics/{rid}/release', {'expected_version': version}, status=409)
        self.assertEqual(self.get('su', '/topics/'+rid)['proposals'], [])
        tid = self.thread()
        self.post('lin', f'/threads/{tid}/share', {'target_id': self.ids['su'], 'title': '请看', 'body': '摘要', 'source_ids': [bundle]}, status=403)

    def test_collection_is_versioned_and_rejects_private_team_references(self):
        private = self.resource()
        self.post('lin', '/resources', {'title': '组合', 'scope': 'team', 'resource_ids': [private]}, status=403)
        bundle = self.post('lin', '/resources', {'title': '个人组合', 'resource_ids': [private]})['id']
        tid = self.thread()
        self.post('lin', f'/threads/{tid}/bindings', {'expected_version': 0, 'included': [bundle, bundle]})
        self.assertEqual(len(self.get('lin', f'/threads/{tid}/context')['resources']), 1)
        rid = self.send('lin', tid, execute=False)
        with patch('accord_api.runtime.agent.stream_answer', side_effect=reply) as call:
            runtime.execute_run(rid)
            self.assertEqual({d['id'] for d in call.call_args.args[1]}, {bundle, private})

    def test_revoke_before_execution_prevents_paid_request_and_retry(self):
        resource = self.resource(scope='team')
        tid = self.thread(peer=True)
        self.post('lin', f'/threads/{tid}/bindings', {'expected_version': 0, 'included': [resource]})
        rid = self.send('lin', tid, execute=False)
        self.post('lin', f'/resources/{resource}/update', {'expected_version': 1, 'title': '收回共享', 'body': '现在仅自己', 'scope': 'private'})
        with patch('accord_api.runtime.agent.stream_answer', side_effect=reply) as call:
            runtime.execute_run(rid)
            call.assert_not_called()
        self.assertEqual(store.query_one('SELECT status FROM accord_runs WHERE id=?', (rid,))['status'], 'error')
        self.post('lin', f'/runs/{rid}/retry', status=403)

    def test_private_work_shared_as_explicit_content_not_raw_history(self):
        tid = self.thread()
        self.send('lin', tid, 'PRIVATE-UNSELECTED-HISTORY')
        shared = self.post('lin', f'/threads/{tid}/share', {'target_id': self.ids['su'], 'title': '请确认', 'body': '明确选中的结论'})['id']
        data = self.get('su', '/threads/'+shared)
        self.assertNotIn('PRIVATE-UNSELECTED-HISTORY', json.dumps(data))
        self.assertIn('明确选中的结论', json.dumps(data, ensure_ascii=False))
        self.get('su', '/threads/'+tid, 404)
        self.get('zhou', '/threads/'+shared, 404)

    def test_two_people_explore_release_decide_and_accept(self):
        rid = self.topic()
        self.get('zhou', '/topics/'+rid, 404)
        a = self.post('lin', f'/topics/{rid}/explorations')['id']
        b = self.post('su', f'/topics/{rid}/explorations')['id']
        self.send('lin', a, 'PRIVATE-A-RESEARCH')
        self.send('su', b, 'PRIVATE-B-RESEARCH')
        self.get('lin', '/threads/'+b, 404)
        self.post('lin', f'/threads/{a}/handoff', status=403)
        pa = self.submit('lin', rid, 'A-PROPOSAL-V1')['id']
        before = self.get('su', '/topics/'+rid)
        self.assertEqual(before['proposals'], [])
        self.assertEqual(before['submitted_count'], 1)
        self.assertNotIn('A-PROPOSAL', json.dumps(before))
        self.post('su', f'/topics/{rid}/release', {'expected_version': before['version']}, status=403)
        self.post('su', f'/topics/{rid}/reviews', status=409)
        self.submit('su', rid, 'B-PROPOSAL-V1')
        self.release(rid)
        published = self.get('lin', '/topics/'+rid)
        self.assertEqual(len(published['proposals']), 2)
        self.get('zhou', '/resources/'+published['proposals'][0]['id'], 404)
        review = self.post('su', f'/topics/{rid}/reviews')['id']
        self.assertEqual(self.get('su', '/threads/'+review)['messages'], [])
        run_id = self.send('su', review, '比较已公开方案', execute=False)
        with patch('accord_api.runtime.agent.stream_answer', side_effect=reply) as call:
            runtime.execute_run(run_id)
            self.assertEqual(call.call_args.args[2], [])
            self.assertNotIn('PRIVATE-A-RESEARCH', json.dumps(call.call_args.args[1]))
            self.assertNotIn('PRIVATE-B-RESEARCH', json.dumps(call.call_args.args[1]))
        self.post('lin', f'/topics/{rid}/decision', {'expected_version': published['version'], 'body': '采用 A，先验证接口。', 'proposal_ids': [pa]})
        task_count = len(store.list_tasks())
        handed = self.post('lin', f'/topics/{rid}/handoff', {'target_id': self.ids['su'], 'task_title': '验证接口'})['id']
        self.assertEqual(len(store.list_tasks()), task_count)
        again = self.post('lin', f'/topics/{rid}/handoff', {'target_id': self.ids['su'], 'task_title': '验证接口'})['id']
        self.assertEqual(handed, again)
        task = self.post('su', f'/threads/{handed}/confirm', {'conclusion': '我来验证接口', 'task_title': '验证接口', 'assignee_id': self.ids['su']})['task_id']
        self.post('lin', f'/tasks/{task}/status', {'status': 'done'}, status=404)
        self.post('su', f'/tasks/{task}/status', {'status': 'done'})

    def test_submission_replacement_and_withdrawal_preserve_versions(self):
        rid = self.topic()
        first = self.submit('lin', rid, 'VERSION-ONE')
        self.post('lin', f'/topics/{rid}/withdraw', {'expected_version': first['submission_version']})
        replacement = self.submit('lin', rid, 'VERSION-TWO', 2)
        self.assertEqual(replacement['version'], 2)
        self.release(rid)
        published = self.get('su', '/topics/'+rid)
        self.assertEqual([p['body'] for p in published['proposals']], ['VERSION-TWO'])
        self.assertEqual(store.query_one('SELECT body FROM accord_proposals WHERE id=?', (first['id'],))['body'], 'VERSION-ONE')

    def test_release_and_submission_race_never_partially_publishes(self):
        rid = self.topic(); self.submit('lin', rid, '先提交')
        version = self.get('lin', '/topics/'+rid)['version']
        def release():
            return self.clients['lin'].post(f'/api/topics/{rid}/release', json={'operation_id': str(uuid4()), 'expected_version': version})
        def submit():
            return self.clients['su'].post(f'/api/topics/{rid}/submit', json={'operation_id': str(uuid4()), 'expected_version': 0, 'title': '同时提交', 'body': '同时提交'})
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(release), pool.submit(submit)]
            statuses = [future.result().status_code for future in futures]
        self.assertIn(statuses, ([200,409], [409,200]))
        topic = self.get('su', '/topics/'+rid)
        self.assertEqual(len(topic['proposals']), 1 if statuses[0] == 200 else 0)

    def test_streamed_tool_calls_read_actual_version_and_accumulate_usage(self):
        resource = self.resource(body='TOOL-ONLY-EVIDENCE-7182')
        tid = self.thread()
        self.post('lin', f'/threads/{tid}/bindings', {'expected_version': 0, 'included': [resource]})
        rid = self.send('lin', tid, execute=False)
        payloads = []
        def handler(request):
            payload = json.loads(request.content); payloads.append(payload)
            if len(payloads) == 1:
                args = json.dumps({'resource_id': resource})
                events = [
                    {'choices':[{'delta':{'tool_calls':[{'index':0,'id':'read_call','function':{'name':'context_read','arguments':args[:10]}}]},'finish_reason':None}]},
                    {'choices':[{'delta':{'tool_calls':[{'index':0,'function':{'arguments':args[10:]}}]},'finish_reason':'tool_calls'}]},
                    {'choices':[],'usage':{'total_tokens':18}}]
            else:
                events = [{'choices':[{'delta':{'content':'根据资料，证据编号为 7182。'},'finish_reason':'stop'}]}, {'choices':[],'usage':{'total_tokens':23}}]
            return httpx.Response(200, content=('\n\n'.join('data: '+json.dumps(e) for e in events)+'\n\ndata: [DONE]\n').encode())
        with patch.dict(os.environ, {'ACCORD_LLM_API_KEY':'test-key','ACCORD_LLM_BASE_URL':'https://provider.test/v1','ACCORD_LLM_MODEL':'test-model'}), patch('accord_api.agent.httpx.Client', return_value=httpx.Client(transport=httpx.MockTransport(handler))):
            runtime.execute_run(rid)
        self.assertEqual(len(payloads), 2)
        self.assertNotIn('TOOL-ONLY-EVIDENCE-7182', json.dumps(payloads[0]))
        self.assertIn('TOOL-ONLY-EVIDENCE-7182', json.dumps(payloads[1]))
        result = self.get('lin', '/threads/'+tid)
        self.assertEqual(result['messages'][-1]['meta']['status'], 'done')
        self.assertEqual(result['messages'][-1]['meta']['usage']['total_tokens'], 41)
        self.assertEqual(result['messages'][-1]['sources'], [resource])
        self.assertEqual(result['tool_calls'][0]['resource_version'], 1)

    def test_tool_cannot_read_unbound_id_or_inject_authority(self):
        resource = self.resource()
        tid = self.thread(); rid = self.send('lin', tid, execute=False)
        snapshot = json.loads(store.query_one('SELECT manifest FROM accord_run_inputs WHERE run_id=?', (rid,))['manifest'])
        tools = context.ToolContext(rid, snapshot)
        self.assertIn('error', tools.execute('denied_id', 'context_read', {'resource_id': resource}))
        self.assertIn('error', tools.execute('denied_role', 'context_list', {'role': 'admin'}))
        self.assertEqual(tools.used, {})
        self.post('lin', f'/runs/{rid}/stop')


if __name__ == '__main__':
    unittest.main()
