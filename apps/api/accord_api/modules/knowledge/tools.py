import json
import re

from pydantic import ValidationError

from accord_api.modules.knowledge.snapshots import validate
from accord_api.modules.knowledge.tool_schemas import TOOL_ARGS, TOOLS
from accord_api.modules.permissions import policy as access
from accord_api.platform.db import database as store
from accord_api.platform.errors import DomainError


class ToolContext:
    schemas = TOOLS

    def __init__(self, rid, manifest_):
        self.rid, self.manifest = rid, manifest_
        self.used, self.chars, self.calls = {}, 0, 0
        self.activity_permissions = {}
        self.person_sources = []

    def check(self):
        with store.lock:
            validate(store.connection(), self.manifest)
            from accord_api.modules.knowledge import person_context

            person_context.validate(
                store.connection(), self.person_sources, self.manifest['audience']
            )
            from accord_api.modules.activity import service as activity

            for uid, version in self.activity_permissions.items():
                if activity.preferences(store.connection(), uid)['version'] != version:
                    raise DomainError(403, '对方已调整工作状态的共享范围，请重新提问。')

    def documents(self):
        with store.lock:
            validate(store.connection(), self.manifest)
            if self.manifest.get('selection_mode') == 'automatic':
                return []  # Only the catalog enters the prompt; bodies require a tool call.
            return [
                access.resource_for(
                    store.connection(), self.manifest['actor_id'], ref['id'], ref['version']
                )
                for ref in self.manifest['resources']
            ]

    def read(self, rid):
        ref = next((r for r in self.manifest['resources'] if r['id'] == rid), None)
        if not ref:
            raise DomainError(404, '资料不在本次可用范围内。')
        return access.resource_for(
            store.connection(), self.manifest['actor_id'], rid, ref['version']
        )

    def execute(self, call_id, name, arguments):
        self.calls += 1
        status, rid, version, result = 'done', '', None, {}
        with store.lock, store.connection():
            db = store.connection()
            validate(db, self.manifest)
            if self.calls > 12 or self.chars >= 24000:
                raise DomainError(422, '已达到本次资料查阅上限，请缩小问题范围。')
            if name not in TOOL_ARGS:
                raise DomainError(422, '工具不在允许范围内。')
            try:
                args = TOOL_ARGS[name].model_validate(arguments)
                if name == 'person_context':
                    from accord_api.modules.knowledge import person_context

                    thread = access.thread_for(
                        self.manifest['actor_id'], self.manifest['thread_id'], db
                    )
                    subject = self.manifest.get('agent_target_id') or thread['target_id']
                    result = (
                        person_context.collect(
                            db,
                            subject,
                            self.manifest['audience'],
                            args.query,
                            exclude_thread=self.manifest['thread_id'],
                            resource_versions={
                                r['id']: r['version'] for r in self.manifest['resources']
                            },
                        )
                        if self.manifest.get('selection_mode') == 'automatic'
                        else {'sources': [], 'coverage': '本轮已指定资料，只使用指定范围。'}
                    )
                    self.person_sources.extend(result['sources'])
                    from accord_api.modules.knowledge.retrieval import public_ref

                    # Preserve the complete evidence trail before any text is streamed.
                    self.manifest['context_sources'] = [
                        public_ref(ref) if ref.get('chunk_id') else ref
                        for ref in self.person_sources
                    ]
                    db.execute(
                        'UPDATE accord_run_inputs SET manifest=? WHERE run_id=?',
                        (json.dumps(self.manifest), self.rid),
                    )
                elif name == 'colleague_status':
                    from accord_api.modules.activity import service as activity

                    thread = access.thread_for(
                        self.manifest['actor_id'], self.manifest['thread_id'], db
                    )
                    subject = self.manifest.get('agent_target_id') or thread['target_id']
                    result = activity.visible(db, self.manifest['actor_id'], subject)
                    if thread['kind'] == 'group':
                        # A private chat title visible to the requester may still be
                        # hidden from another group member. Apply the whole audience.
                        if result['work'] and any(
                            activity.visible(db, member, subject)['work'] != result['work']
                            for member in access.participants(thread)
                        ):
                            result['work'] = None
                        shared = []
                        for task in result['shared_tasks']:
                            try:
                                for member in access.participants(thread):
                                    access.thread_for(member, task['thread_id'], db)
                                shared.append(task)
                            except DomainError:
                                pass
                        result['shared_tasks'] = shared
                        result['progress'] = {
                            'total': len(shared),
                            'completed': sum(t['status'] == 'done' for t in shared),
                            'scope': '群成员共同可见',
                        }
                    self.activity_permissions[subject] = result['permission_version']
                elif name == 'context_list':
                    resources = []
                    for ref in self.manifest['resources']:
                        item = self.read(ref['id'])
                        owner = db.execute(
                            'SELECT person_name FROM units WHERE id=?', (item['owner_id'],)
                        ).fetchone()
                        resources.append(
                            {
                                **ref,
                                'owner_id': item['owner_id'],
                                'owner_name': owner['person_name'] if owner else '',
                                'scope': item['scope'],
                                'kind': item['kind'],
                            }
                        )
                    result = {
                        'resources': resources,
                        'coverage': {
                            'resource_count': len(resources),
                            'complete_user_archive': False,
                            'history_scope': 'current_conversation',
                            'meaning': '只覆盖本次获准资料与当前对话；空结果不表示本人没有工作或其他资料。',
                        },
                    }
                elif name == 'context_read':
                    rid = args.resource_id
                    resource = self.read(rid)
                    version = resource['version']
                    snippet = resource['body'][
                        args.offset : args.offset + min(args.length, 24000 - self.chars)
                    ]
                    result = {
                        'id': rid,
                        'title': resource['title'],
                        'version': version,
                        'offset': args.offset,
                        'content': snippet,
                        'owner_id': resource['owner_id'],
                        'scope': resource['scope'],
                        'next_offset': args.offset + len(snippet)
                        if args.offset + len(snippet) < len(resource['body'])
                        else None,
                    }
                    if snippet:
                        self.used[rid] = {'id': rid, 'title': resource['title'], 'version': version}
                else:
                    terms = set(
                        re.findall(r'[a-zA-Z0-9]{2,}|[\u4e00-\u9fff]{1,2}', args.query.lower())
                    )
                    hits = []
                    for ref in self.manifest['resources']:
                        resource = self.read(ref['id'])
                        haystack = (resource['title'] + '\n' + resource['body']).lower()
                        score = sum(term in haystack for term in terms)
                        if score:
                            position = min(
                                (
                                    resource['body'].lower().find(term)
                                    for term in terms
                                    if term in resource['body'].lower()
                                ),
                                default=0,
                            )
                            offset = max(0, position - 120)
                            hits.append(
                                (
                                    score,
                                    {
                                        'id': ref['id'],
                                        'version': resource['version'],
                                        'title': resource['title'],
                                        'offset': offset,
                                        'content': resource['body'][offset : offset + 1000],
                                    },
                                )
                            )
                    found = [hit for _, hit in sorted(hits, key=lambda h: -h[0])[:4]]
                    result = {'results': found}
                    for hit in found:
                        if hit['content']:
                            self.used[hit['id']] = {k: hit[k] for k in ('id', 'title', 'version')}
            except (ValidationError, DomainError):
                status, result = (
                    'denied',
                    {'error': '参数无效，或资料不在本次可用范围内。请使用当前资料目录中的 ID。'},
                )
            encoded = json.dumps(result, ensure_ascii=False)
            if self.chars + len(encoded) > 28000:
                raise DomainError(422, '已达到本次资料查阅上限，请缩小问题范围。')
            self.chars += len(encoded)
            db.execute(
                'INSERT INTO accord_tool_calls VALUES(?,?,?,?,?,?,?,?,?)',
                (
                    store.new_id('tool'),
                    self.rid,
                    call_id,
                    name,
                    rid,
                    version,
                    status,
                    len(encoded),
                    store.now(),
                ),
            )
            return result
