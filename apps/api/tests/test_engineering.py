"""Refactor acceptance: API contracts, dependency direction and context provenance."""

import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import test_collaboration as fixtures
import test_workflows as workflows

from accord_api.app import app
from accord_api.modules import knowledge
from accord_api.modules.activity import service as activity
from accord_api.modules.agent_runs import generation
from accord_api.platform.db import database

ROOT = Path(__file__).resolve().parents[1]


def resolved_contract(document):
    def resolve(value):
        if isinstance(value, list):
            return [resolve(item) for item in value]
        if isinstance(value, dict):
            if '$ref' in value:
                return resolve(document['components']['schemas'][value['$ref'].split('/')[-1]])
            return {key: resolve(item) for key, item in value.items() if key != 'operationId'}
        return value

    return resolve(document['paths'])


class EngineeringTests(unittest.TestCase):
    def test_existing_http_contracts_are_preserved(self):
        expected = json.loads((ROOT / 'tests/fixtures/http-contract-v1.json').read_text())
        current = resolved_contract(app.openapi())
        # New feature routes may be added; every baseline route retains its exact contract.
        self.assertEqual({path: current.get(path) for path in expected}, expected)

    def test_feature_imports_do_not_initialize_a_database(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'not-created'
            env = dict(os.environ, ACCORD_DATA_DIR=str(target), PYTHONPATH=str(ROOT))
            code = """
import importlib, pkgutil
import accord_api.modules
for item in pkgutil.walk_packages(accord_api.modules.__path__, 'accord_api.modules.'):
    importlib.import_module(item.name)
from accord_api.platform.config import database_path
print(database_path())
"""
            result = subprocess.run(
                [sys.executable, '-c', code], env=env, capture_output=True, text=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(Path(result.stdout.strip()), target.resolve() / 'data/pool.db')
            self.assertFalse(target.exists())

    def test_dependency_direction_is_enforced(self):
        for path in (ROOT / 'accord_api').rglob('*.py'):
            rel = path.relative_to(ROOT / 'accord_api')
            for node in ast.walk(ast.parse(path.read_text())):
                if not isinstance(node, ast.ImportFrom):
                    continue
                module = node.module or ''
                if rel.parts[0] == 'platform':
                    self.assertFalse(module.startswith(('accord_api.modules', 'fastapi')), str(rel))
                if rel.parts[0] == 'modules':
                    self.assertNotEqual(module, 'accord_api.main', str(rel))
                    if path.name not in ('api.py', 'session.py') and not path.name.endswith(
                        '_api.py'
                    ):
                        self.assertFalse(module.startswith('fastapi'), str(rel))

    def test_group_prompt_does_not_offer_a_private_handoff_button(self):
        class Context:
            manifest = {'resources': [], 'purpose': 'ordinary', 'is_group': True}

        with patch.object(generation.provider, 'stream_answer', return_value={}) as provider:
            generation.stream_answer(
                '总结',
                [],
                [],
                '同事',
                True,
                lambda *args: None,
                lambda: False,
                tool_context=Context(),
            )
        system = provider.call_args.args[0][0]['content']
        self.assertIn('请其在本群补充', system)
        self.assertIn('不能推断本人没有工作', system)
        self.assertNotIn('可建议使用找本人', system)


class ContextCoverageTests(unittest.TestCase):
    post = workflows.WorkflowTests.post
    get = workflows.WorkflowTests.get

    @classmethod
    def setUpClass(cls):
        if not hasattr(fixtures.CollaborationTests, 'ids'):
            fixtures.CollaborationTests.setUpClass()
        cls.clients, cls.ids = fixtures.CollaborationTests.clients, fixtures.CollaborationTests.ids

    def tools(self, tid, actor='lin', target='su'):
        result = self.post(
            actor, f'/groups/{tid}/messages', {'body': '查看共享信息', 'agent_id': self.ids[target]}
        )
        rid = result['run_id']
        self.addCleanup(lambda: self.post(actor, f'/runs/{rid}/stop'))
        manifest = json.loads(
            database.query_one('SELECT manifest FROM accord_run_inputs WHERE run_id=?', (rid,))[
                'manifest'
            ]
        )
        return knowledge.ToolContext(rid, manifest)

    def group(self):
        return self.post('lin', '/groups', {'member_ids': [self.ids['su'], self.ids['zhou']]})['id']

    def test_tool_catalog_explains_coverage_and_preserves_source_owner(self):
        rid = self.post(
            'su', '/resources', {'title': '来源归属验收', 'body': '可验证的内容', 'scope': 'team'}
        )['id']
        tool = self.tools(self.group())
        result = tool.execute('catalog-' + uuid4().hex, 'context_list', {})
        self.assertFalse(result['coverage']['complete_user_archive'])
        self.assertEqual(result['coverage']['history_scope'], 'current_conversation')
        item = next(item for item in result['resources'] if item['id'] == rid)
        self.assertEqual(item['owner_id'], self.ids['su'])
        self.assertEqual(item['scope'], 'team')
        self.assertNotIn('body', item)
        read = tool.execute('read-' + uuid4().hex, 'context_read', {'resource_id': rid})
        self.assertEqual(read['content'], '可验证的内容')
        self.assertEqual(read['owner_id'], self.ids['su'])

    def test_group_status_cannot_reveal_a_pair_private_chat_title(self):
        tid = self.post(
            'su', '/threads', {'target_id': self.ids['lin'], 'title': 'PAIR-PRIVATE-TITLE'}
        )['id']
        database.execute("UPDATE accord_threads SET status='human' WHERE id=?", (tid,))
        pref = activity.preferences(database.connection(), self.ids['su'])
        self.post(
            'su',
            '/profile/activity',
            {'automatic': True, 'work_title': True, 'expected_version': pref['version']},
        )
        self.addCleanup(
            lambda: self.post(
                'su',
                '/profile/activity',
                {
                    'automatic': False,
                    'expected_version': activity.preferences(database.connection(), self.ids['su'])[
                        'version'
                    ],
                },
            )
        )
        self.post(
            'su', '/presence', {'client_id': uuid4().hex, 'surface': 'chat', 'thread_id': tid}
        )
        self.assertEqual(
            activity.visible(database.connection(), self.ids['lin'], self.ids['su'])['work'][
                'title'
            ],
            'PAIR-PRIVATE-TITLE',
        )
        tool = self.tools(self.group())
        result = tool.execute('status-' + uuid4().hex, 'colleague_status', {})
        self.assertIsNone(result['work'])
        self.assertNotIn('PAIR-PRIVATE-TITLE', json.dumps(result))
