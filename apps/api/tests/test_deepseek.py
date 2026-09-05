import json
import os
import unittest
from unittest.mock import patch

import httpx

from accord_api.modules.agent_runs import generation as agent


class ReadContext:
    schemas = [{'type': 'function', 'function': {'name': 'context_read', 'parameters': {'type': 'object', 'properties': {'resource_id': {'type': 'string'}}}}}]
    manifest = {'resources': [{'id':'r1','title':'Check'}], 'purpose':'ordinary'}

    def __init__(self):
        self.used = {}

    def check(self):
        pass

    def execute(self, call_id, name, args):
        assert name == 'context_read' and args == {'resource_id':'r1'}
        self.used['r1'] = {'id':'r1','title':'Check','version':1}
        return {'content':'The check value is seven.'}


class DeepSeekTests(unittest.TestCase):
    def run_stream(self, handler, **kwargs):
        client = httpx.Client(transport=httpx.MockTransport(handler))
        config = {'ACCORD_LLM_PROVIDER':'deepseek', 'ACCORD_LLM_BASE_URL':'https://api.deepseek.com',
                  'ACCORD_LLM_MODEL':'deepseek-v4-pro', 'ACCORD_LLM_API_KEY':'test-only',
                  'ACCORD_LLM_REASONING_EFFORT':'max', 'ACCORD_LLM_ENABLE_THINKING':'false'}
        with patch.dict(os.environ, config), patch('accord_api.platform.ai.provider.httpx.Client', return_value=client):
            return agent.stream_answer('Read the value', [], [{'role':'assistant','content':'Earlier answer','reasoning_content':'earlier trace'}],
                'Owner', False, kwargs.pop('on_delta', lambda *a:None), kwargs.pop('cancelled', lambda:False), **kwargs)

    @staticmethod
    def response(events):
        return httpx.Response(200, content=('\n\n'.join('data: '+json.dumps(event) for event in events)+'\n\ndata: [DONE]\n\n').encode())

    def test_max_reasoning_tool_loop_and_prior_history_roundtrip(self):
        requests, phases, updates, usage_updates = [], [], [], []
        def handler(request):
            payload = json.loads(request.content)
            requests.append(payload)
            if len(requests) == 1:
                events = [
                    {'choices':[{'delta':{'reasoning_content':'read trace'}}]},
                    {'choices':[{'delta':{'tool_calls':[{'index':0,'id':'call1','function':{'name':'context_read','arguments':'{"resource_id":'}}]}}]},
                    {'choices':[{'delta':{'tool_calls':[{'index':0,'function':{'arguments':'"r1"}'}}]},'finish_reason':'tool_calls'}]},
                ]
            else:
                events = [{'choices':[{'delta':{'reasoning_content':'answer trace'}}]},
                    {'choices':[{'delta':{'content':'Seven.'},'finish_reason':'stop'}]}]
            events.append({'choices':[], 'usage':{'prompt_tokens':10,'completion_tokens':20,'total_tokens':30,
                'completion_tokens_details':{'reasoning_tokens':15}}})
            return self.response(events)
        result = self.run_stream(handler, tool_context=ReadContext(), on_phase=phases.append,
                                 on_delta=lambda text,sources:updates.append(text), on_usage=usage_updates.append)
        for payload in requests:
            self.assertEqual(payload['thinking'], {'type':'enabled'})
            self.assertEqual(payload['reasoning_effort'], 'max')
            self.assertNotIn('enable_thinking', payload)
        self.assertEqual(requests[0]['messages'][-2]['reasoning_content'], 'earlier trace')
        self.assertEqual(requests[1]['messages'][-2]['reasoning_content'], 'read trace')
        self.assertEqual(requests[1]['messages'][-1]['tool_call_id'], 'call1')
        self.assertEqual(phases, ['thinking','reading','thinking','answering'])
        self.assertEqual(updates, ['Seven.'])
        self.assertEqual(result['reasoning_content'], 'read traceanswer trace')
        self.assertEqual(result['usage']['reasoning_tokens'], 30)
        self.assertEqual(usage_updates[-1]['total_tokens'], 60)
        self.assertEqual(result['sources'], ['r1'])

    def test_each_supported_effort_reaches_provider(self):
        for effort in agent.REASONING_EFFORTS:
            def handler(request):
                self.assertEqual(json.loads(request.content)['reasoning_effort'], effort)
                return self.response([{'choices':[{'delta':{'content':'OK'},'finish_reason':'stop'}]}])
            self.run_stream(handler, reasoning_effort=effort)

    def test_stop_during_reasoning_emits_no_answer(self):
        stopped, updates = [False], []
        def phase(_):
            stopped[0] = True
        events = [{'choices':[{'delta':{'reasoning_content':'internal trace'}}]},
                  {'choices':[{'delta':{'content':'should not appear'},'finish_reason':'stop'}]}]
        with self.assertRaises(agent.ModelError) as error:
            self.run_stream(lambda r:self.response(events), on_phase=phase, cancelled=lambda:stopped[0], on_delta=lambda *a:updates.append(a))
        self.assertEqual(error.exception.code, 'cancelled')
        self.assertEqual(updates, [])

    def test_reasoning_budget_exhaustion_is_not_a_success(self):
        events = [{'choices':[{'delta':{'reasoning_content':'unfinished'},'finish_reason':'length'}]}]
        with self.assertRaises(agent.ModelError) as error:
            self.run_stream(lambda r:self.response(events))
        self.assertEqual(error.exception.code, 'reasoning_limit')

    def test_provider_failures_are_sanitized(self):
        for status, code in ((401,'authorization'),(402,'balance'),(429,'rate_limit'),(500,'upstream')):
            with self.assertRaises(agent.ModelError) as error:
                self.run_stream(lambda r:httpx.Response(status, content=b'credential-like-secret'))
            self.assertEqual(error.exception.code, code)
            self.assertNotIn('credential-like-secret', str(error.exception))
