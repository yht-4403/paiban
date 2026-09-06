from accord_api.modules import knowledge as context
from accord_api.modules.activity import service as activity
from accord_api.modules.agent_runs import generation as agent
from accord_api.modules.agent_runs import service as runtime
from accord_api.modules.collaboration import groups as groups
from accord_api.modules.identity import repository as identity_repository
from accord_api.modules.identity import service as auth
from accord_api.modules.permissions.policy import thread_for
from accord_api.modules.preferences import service as model_settings
from accord_api.modules.topics import service as topics
from accord_api.modules.workspace import service as workspace
from accord_api.platform.db import database as store
from accord_api.platform.errors import DomainError


def public_units(viewer):
    return [
        {k: u[k] for k in ('id', 'person_name', 'agent_name', 'window', 'tags')}
        for u in identity_repository.list_units()
        if auth.shares_account_roster(viewer, u['id'])
    ]


def state(*, uid):
    with store.lock:
        db = store.connection()
        threads = []
        for row in db.execute(
            "SELECT id FROM accord_threads WHERE kind!='group' AND (owner_id=? OR target_id=?) ORDER BY updated_at DESC",
            (uid, uid),
        ).fetchall():
            try:
                item = thread_for(uid, row['id'], db)
                last = db.execute(
                    "SELECT * FROM messages WHERE conversation_id=? AND from_kind!='system' AND body!='' ORDER BY rowid DESC LIMIT 1",
                    (item['id'],),
                ).fetchone()
                from accord_api.modules.collaboration.repository import row_msg

                item['preview'] = row_msg(last, uid, db)['body'][:70] if last else ''
                threads.append(item)
            except DomainError:
                pass
        tasks = [
            dict(r)
            for r in db.execute(
                """SELECT t.*,a.creator_id,a.thread_id FROM tasks t JOIN accord_task_acl a ON a.task_id=t.id
            WHERE a.creator_id=? OR t.assignee_id=? ORDER BY t.created_at DESC""",
                (uid, uid),
            )
            if auth.shares_account_roster(r['creator_id'], r['assignee_id'])
            if any(t['id'] == r['thread_id'] for t in threads)
            or db.execute(
                'SELECT 1 FROM accord_group_members WHERE thread_id=? AND member_id=?',
                (r['thread_id'], uid),
            ).fetchone()
        ]
        archived = {
            r['thread_id']
            for r in db.execute(
                'SELECT thread_id FROM accord_thread_archives WHERE owner_id=?', (uid,)
            )
        }
        from accord_api.modules.coordination.service import list_flows, sharing
        from accord_api.modules.knowledge.connectors import list_connections

        selected_model = model_settings.public_settings(db, uid)

        return {
            'flows': list_flows(db, uid),
            'context_sharing': sharing(uid),
            'content_connections': list_connections(db, uid),
            'groups': groups.list_groups(db, uid),
            'archived_threads': [t for t in threads if t['id'] in archived],
            'me': uid,
            'members': [
                {**member, 'activity': activity.visible(db, uid, member['id'])}
                for member in public_units(uid)
            ],
            'threads': [t for t in threads if t['id'] not in archived],
            'tasks': [
                topics.task_projection(
                    db,
                    uid,
                    {**task, 'priority': activity.task_priority(db, task['id'])},
                )
                for task in tasks
            ],
            'documents': context.available(db, uid),
            'folders': workspace.folders(db, uid),
            'topics': topics.list_rounds(db, uid),
            'model': {
                'mode': 'model' if agent.configured() else 'unavailable',
                **runtime.usage_for(uid),
                **selected_model,
                'label': selected_model['label'] if agent.configured() else '模型未连接',
            },
            'activity_preferences': activity.preferences(db, uid),
            'account': auth.account(uid),
            'project': {'name': auth.workspace_name()},
        }
