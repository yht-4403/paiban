"""One-time product-name migration for the six disposable fixed-account workspaces."""

import hashlib

from accord_api.platform.db import database as store

MARKER = 'paiban_fixed_account_brand_v2'
REPLACEMENTS = (
    ('Accord 工作台', '拍办工作台'),
    ('Accord 路演', '拍办路演'),
    ('本次 Accord', '本次拍办'),
    ('在 Accord 中', '在拍办中'),
    ('负责 Accord 的', '负责拍办的'),
    ('为什么要做 Accord', '为什么要做拍办'),
    ('Accord 为', '拍办为'),
    ('Accord 面向', '拍办面向'),
    ('Accord 的', '拍办的'),
    ('Accord', '拍办'),
)


def _brand_text(value):
    for previous, current in REPLACEMENTS:
        value = value.replace(previous, current)
    return value


def _replace_columns(db, table, columns, where):
    for column in columns:
        rows = db.execute(
            f"SELECT rowid,{column} FROM {table} WHERE ({where}) AND instr({column},?)>0",
            ('Accord',),
        ).fetchall()
        for row in rows:
            db.execute(
                f'UPDATE {table} SET {column}=? WHERE rowid=?',
                (_brand_text(row[column]), row['rowid']),
            )


def initialize():
    with store.lock, store.connection() as db:
        if db.execute('SELECT 1 FROM project_state WHERE key=?', (MARKER,)).fetchone():
            return

        fixed_thread = "owner_id LIKE 'fixed_%' OR target_id LIKE 'fixed_%'"
        fixed_task = "assignee_id LIKE 'fixed_%' OR id IN (SELECT task_id FROM accord_task_acl WHERE creator_id LIKE 'fixed_%')"
        fixed_flow = "owner_id LIKE 'fixed_%'"
        _replace_columns(db, 'accord_threads', ('title', 'handoff_note'), fixed_thread)
        _replace_columns(db, 'accord_flows', ('title', 'body', 'result', 'evidence', 'error'), fixed_flow)
        _replace_columns(
            db,
            'accord_flow_actions',
            ('title', 'detail'),
            "flow_id IN (SELECT id FROM accord_flows WHERE owner_id LIKE 'fixed_%')",
        )
        _replace_columns(
            db,
            'tasks',
            ('title', 'detail', 'assign_reason', 'module', 'how_to', 'artifact', 'await_note'),
            fixed_task,
        )
        _replace_columns(
            db,
            'messages',
            ('body', 'meta'),
            "from_unit LIKE 'fixed_%' OR conversation_id IN (SELECT id FROM accord_threads WHERE owner_id LIKE 'fixed_%' OR target_id LIKE 'fixed_%')",
        )
        _replace_columns(db, 'artifacts', ('title', 'body'), "unit_id LIKE 'fixed_%'")
        _replace_columns(db, 'memories', ('title', 'body', 'source'), "unit_id LIKE 'fixed_%'")
        _replace_columns(db, 'meeting_msgs', ('body',), "from_unit LIKE 'fixed_%'")
        _replace_columns(db, 'accord_rounds', ('title',), "owner_id LIKE 'fixed_%'")
        _replace_columns(db, 'accord_proposals', ('title', 'body'), "author_id LIKE 'fixed_%'")
        _replace_columns(db, 'accord_operations', ('result',), "actor LIKE 'fixed_%'")

        versions = db.execute(
            """SELECT v.rowid,v.title,v.body,v.refs FROM accord_resource_versions v
            JOIN accord_resources r ON r.id=v.resource_id
            WHERE r.owner_id LIKE 'fixed_%' AND (instr(v.title,'Accord')>0 OR instr(v.body,'Accord')>0)"""
        ).fetchall()
        for version in versions:
            title = _brand_text(version['title'])
            body = _brand_text(version['body'])
            db.execute(
                'UPDATE accord_resource_versions SET title=?,body=?,digest=? WHERE rowid=?',
                (
                    title,
                    body,
                    hashlib.sha256((body + version['refs']).encode()).hexdigest(),
                    version['rowid'],
                ),
            )
        db.execute(
            "INSERT OR IGNORE INTO accord_index_queue SELECT 'resource',id FROM accord_resources WHERE owner_id LIKE 'fixed_%'"
        )
        db.execute(
            'INSERT INTO project_state(key,value,updated_at) VALUES(?,?,?)',
            (MARKER, 'done', store.now()),
        )
