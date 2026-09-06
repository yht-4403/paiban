"""One-time display-name migration for the built-in demo accounts."""

import hashlib

from accord_api.platform.db import database as store

MARKER = 'paiban_fixed_demo_member_name_v2'
PREVIOUS_NAME = '舒奥'
CURRENT_NAME = '书傲'


def _rename(value):
    return value.replace(PREVIOUS_NAME, CURRENT_NAME)


def _replace_columns(db, table, columns, where):
    for column in columns:
        rows = db.execute(
            f"SELECT rowid,{column} FROM {table} WHERE ({where}) AND instr({column},?)>0",
            (PREVIOUS_NAME,),
        ).fetchall()
        for row in rows:
            db.execute(
                f'UPDATE {table} SET {column}=? WHERE rowid=?',
                (_rename(row[column]), row['rowid']),
            )


def initialize():
    with store.lock, store.connection() as db:
        if db.execute('SELECT 1 FROM project_state WHERE key=?', (MARKER,)).fetchone():
            return

        demo_thread = "owner_id LIKE 'fixed_demo_%' OR target_id LIKE 'fixed_demo_%'"
        demo_task = (
            "assignee_id LIKE 'fixed_demo_%' OR id IN "
            "(SELECT task_id FROM accord_task_acl WHERE creator_id LIKE 'fixed_demo_%')"
        )
        demo_flow = "owner_id LIKE 'fixed_demo_%'"

        _replace_columns(
            db,
            'units',
            ('person_name', 'agent_name', 'tags', 'memory', 'workflows'),
            "id='fixed_demo_shuao'",
        )
        _replace_columns(
            db,
            'accord_threads',
            ('title', 'handoff_note'),
            demo_thread,
        )
        _replace_columns(
            db,
            'messages',
            ('body', 'meta'),
            "from_unit LIKE 'fixed_demo_%' OR conversation_id IN "
            f'(SELECT id FROM accord_threads WHERE {demo_thread})',
        )
        _replace_columns(
            db,
            'accord_runs',
            ('reasoning_content',),
            "actor_id LIKE 'fixed_demo_%' OR thread_id IN "
            f'(SELECT id FROM accord_threads WHERE {demo_thread})',
        )
        _replace_columns(
            db,
            'accord_run_inputs',
            ('manifest',),
            "run_id IN (SELECT id FROM accord_runs WHERE actor_id LIKE 'fixed_demo_%')",
        )
        _replace_columns(
            db,
            'accord_thread_attachments',
            ('filename', 'content'),
            "owner_id LIKE 'fixed_demo_%' OR thread_id IN "
            f'(SELECT id FROM accord_threads WHERE {demo_thread})',
        )
        _replace_columns(
            db,
            'accord_flows',
            ('title', 'body', 'result', 'evidence', 'error'),
            demo_flow,
        )
        _replace_columns(
            db,
            'accord_flow_actions',
            ('title', 'detail'),
            "flow_id IN (SELECT id FROM accord_flows WHERE owner_id LIKE 'fixed_demo_%')",
        )
        _replace_columns(
            db,
            'tasks',
            ('title', 'detail', 'assign_reason', 'module', 'how_to', 'artifact', 'await_note'),
            demo_task,
        )
        _replace_columns(db, 'artifacts', ('title', 'body', 'author'), "unit_id LIKE 'fixed_demo_%'")
        _replace_columns(db, 'memories', ('title', 'body', 'source'), "unit_id LIKE 'fixed_demo_%'")
        _replace_columns(db, 'meeting_msgs', ('body',), "from_unit LIKE 'fixed_demo_%'")
        _replace_columns(db, 'duty_log', ('role', 'content'), "unit_id LIKE 'fixed_demo_%'")
        _replace_columns(db, 'scratch', ('title',), "unit_id LIKE 'fixed_demo_%'")
        _replace_columns(
            db,
            'routes',
            ('question', 'answer'),
            "from_unit LIKE 'fixed_demo_%' OR to_unit LIKE 'fixed_demo_%'",
        )
        _replace_columns(db, 'accord_rounds', ('title',), "owner_id LIKE 'fixed_demo_%'")
        _replace_columns(
            db,
            'accord_proposals',
            ('title', 'body'),
            "author_id LIKE 'fixed_demo_%'",
        )
        _replace_columns(db, 'accord_operations', ('result',), "actor LIKE 'fixed_demo_%'")
        _replace_columns(db, 'accord_folders', ('name',), "owner_id LIKE 'fixed_demo_%'")
        _replace_columns(
            db,
            'accord_content_connections',
            ('title',),
            "owner_id LIKE 'fixed_demo_%'",
        )
        _replace_columns(
            db,
            'accord_content_imports',
            ('filename',),
            "owner_id LIKE 'fixed_demo_%'",
        )

        versions = db.execute(
            """SELECT v.rowid,v.title,v.body,v.refs FROM accord_resource_versions v
            JOIN accord_resources r ON r.id=v.resource_id
            WHERE r.owner_id LIKE 'fixed_demo_%'
            AND (instr(v.title,?)>0 OR instr(v.body,?)>0)""",
            (PREVIOUS_NAME, PREVIOUS_NAME),
        ).fetchall()
        for version in versions:
            title = _rename(version['title'])
            body = _rename(version['body'])
            db.execute(
                'UPDATE accord_resource_versions SET title=?,body=?,digest=? WHERE rowid=?',
                (
                    title,
                    body,
                    hashlib.sha256((body + version['refs']).encode()).hexdigest(),
                    version['rowid'],
                ),
            )
        # Search chunks are derived data. Remove the stale spelling before queueing
        # fresh records so the old display name does not survive in inactive rows.
        db.execute(
            "DELETE FROM accord_content_fts WHERE chunk_id IN "
            "(SELECT id FROM accord_content_chunks WHERE owner_id LIKE 'fixed_demo_%')"
        )
        db.execute("DELETE FROM accord_content_chunks WHERE owner_id LIKE 'fixed_demo_%'")
        db.execute(
            "INSERT OR IGNORE INTO accord_index_queue "
            "SELECT 'resource',id FROM accord_resources WHERE owner_id LIKE 'fixed_demo_%'"
        )
        db.execute(
            "INSERT OR IGNORE INTO accord_index_queue "
            "SELECT 'message',m.id FROM messages m JOIN accord_threads t "
            "ON t.id=m.conversation_id WHERE t.owner_id LIKE 'fixed_demo_%' "
            "OR t.target_id LIKE 'fixed_demo_%'"
        )
        db.execute(
            'INSERT INTO project_state(key,value,updated_at) VALUES(?,?,?)',
            (MARKER, 'done', store.now()),
        )
