from accord_api.platform.db import database as store


def initialize():
    with store.lock, store.connection() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS accord_context_grants(
          owner_id TEXT NOT NULL, source_kind TEXT NOT NULL, source_id TEXT NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1,
          PRIMARY KEY(owner_id,source_kind,source_id));
        CREATE TABLE IF NOT EXISTS accord_flows(
          id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, kind TEXT NOT NULL,
          title TEXT NOT NULL, body TEXT NOT NULL, member_ids TEXT NOT NULL,
          source_ids TEXT NOT NULL DEFAULT '[]',
          status TEXT NOT NULL DEFAULT 'queued', result TEXT NOT NULL DEFAULT '{}',
          evidence TEXT NOT NULL DEFAULT '[]', error TEXT NOT NULL DEFAULT '',
          thread_id TEXT NOT NULL DEFAULT '', task_id TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS accord_flow_actions(
          id TEXT PRIMARY KEY, flow_id TEXT NOT NULL, assignee_id TEXT NOT NULL,
          title TEXT NOT NULL, detail TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'suggested',
          task_id TEXT NOT NULL DEFAULT '', UNIQUE(flow_id,assignee_id,title));
        CREATE TABLE IF NOT EXISTS accord_flow_memories(
          flow_id TEXT NOT NULL, owner_id TEXT NOT NULL, resource_id TEXT NOT NULL,
          PRIMARY KEY(flow_id,owner_id));
        CREATE TABLE IF NOT EXISTS accord_flow_followups(
          flow_id TEXT PRIMARY KEY, status TEXT NOT NULL,
          next_flow_id TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS accord_flow_chat_close ON accord_flows(thread_id)
          WHERE kind='chat_summary';
        CREATE TABLE IF NOT EXISTS accord_flow_calls(
          id TEXT PRIMARY KEY, flow_id TEXT NOT NULL, person_id TEXT NOT NULL,
          status TEXT NOT NULL, source_count INTEGER NOT NULL DEFAULT 0,
          usage TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL);
        """)
        flow_columns = {row['name'] for row in db.execute('PRAGMA table_info(accord_flows)')}
        if 'source_ids' not in flow_columns:
            db.execute("ALTER TABLE accord_flows ADD COLUMN source_ids TEXT NOT NULL DEFAULT '[]'")
        unique_thread = any(
            index['unique']
            and [r['name'] for r in db.execute('PRAGMA index_info("' + index['name'] + '")')]
            == ['thread_id']
            for index in db.execute('PRAGMA index_list(accord_task_acl)').fetchall()
        )
        if unique_thread:
            # Preserve existing ACLs atomically while permitting multiple actions per meeting.
            columns = [r['name'] for r in db.execute('PRAGMA table_info(accord_task_acl)')]
            if columns != ['task_id', 'creator_id', 'thread_id']:
                raise RuntimeError('待办权限表结构已改变，需要先核对迁移。')
            db.execute(
                'CREATE TABLE accord_task_acl_next(task_id TEXT PRIMARY KEY, creator_id TEXT NOT NULL, thread_id TEXT NOT NULL)'
            )
            db.execute(
                'INSERT INTO accord_task_acl_next SELECT task_id,creator_id,thread_id FROM accord_task_acl'
            )
            db.execute('DROP TABLE accord_task_acl')
            db.execute('ALTER TABLE accord_task_acl_next RENAME TO accord_task_acl')
        db.execute(
            'CREATE INDEX IF NOT EXISTS accord_task_acl_thread ON accord_task_acl(thread_id)'
        )
