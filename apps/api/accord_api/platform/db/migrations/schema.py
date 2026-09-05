import hashlib

from accord_api.platform.db import database as store


def initialize():
    with store.lock, store.connection():
        db = store.connection()
        db.executescript("""
          CREATE TABLE IF NOT EXISTS accord_schema_versions(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS accord_folders(
            id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, name TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS accord_placements(
            owner_id TEXT NOT NULL, thread_id TEXT NOT NULL, folder_id TEXT NOT NULL DEFAULT '',
            version INTEGER NOT NULL, PRIMARY KEY(owner_id,thread_id));
          CREATE TABLE IF NOT EXISTS accord_group_members(
            thread_id TEXT NOT NULL, member_id TEXT NOT NULL, joined_after INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(thread_id,member_id));
          CREATE TABLE IF NOT EXISTS accord_thread_archives(
            owner_id TEXT NOT NULL, thread_id TEXT NOT NULL, created_at TEXT NOT NULL,
            PRIMARY KEY(owner_id,thread_id));
          CREATE TABLE IF NOT EXISTS accord_bindings(
            owner_id TEXT NOT NULL, target_kind TEXT NOT NULL, target_id TEXT NOT NULL,
            included TEXT NOT NULL DEFAULT '[]', excluded TEXT NOT NULL DEFAULT '[]',
            version INTEGER NOT NULL, PRIMARY KEY(owner_id,target_kind,target_id));
          CREATE TABLE IF NOT EXISTS accord_context_folders(
            owner_id TEXT NOT NULL, thread_id TEXT NOT NULL, folder_id TEXT NOT NULL,
            PRIMARY KEY(owner_id,thread_id,folder_id));
          CREATE TABLE IF NOT EXISTS accord_resources(
            id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, kind TEXT NOT NULL,
            scope TEXT NOT NULL, round_id TEXT NOT NULL DEFAULT '',
            version INTEGER NOT NULL DEFAULT 1, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS accord_resource_versions(
            resource_id TEXT NOT NULL, version INTEGER NOT NULL, title TEXT NOT NULL,
            body TEXT NOT NULL, refs TEXT NOT NULL DEFAULT '[]', digest TEXT NOT NULL,
            created_at TEXT NOT NULL, PRIMARY KEY(resource_id,version));
          CREATE TABLE IF NOT EXISTS accord_rounds(
            id TEXT PRIMARY KEY, title TEXT NOT NULL, owner_id TEXT NOT NULL,
            brief_id TEXT NOT NULL, stage TEXT NOT NULL DEFAULT 'exploring',
            deadline TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL DEFAULT 1,
            decision_id TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS accord_round_members(
            round_id TEXT NOT NULL, member_id TEXT NOT NULL, PRIMARY KEY(round_id,member_id));
          CREATE TABLE IF NOT EXISTS accord_thread_scopes(
            thread_id TEXT PRIMARY KEY, purpose TEXT NOT NULL, round_id TEXT NOT NULL DEFAULT '');
          CREATE TABLE IF NOT EXISTS accord_proposals(
            id TEXT PRIMARY KEY, round_id TEXT NOT NULL, author_id TEXT NOT NULL,
            version INTEGER NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
            sources TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL,
            UNIQUE(round_id,author_id,version));
          CREATE TABLE IF NOT EXISTS accord_submissions(
            round_id TEXT NOT NULL, member_id TEXT NOT NULL, proposal_id TEXT NOT NULL DEFAULT '',
            version INTEGER NOT NULL, PRIMARY KEY(round_id,member_id));
          CREATE TABLE IF NOT EXISTS accord_releases(
            round_id TEXT NOT NULL, proposal_id TEXT NOT NULL, resource_id TEXT NOT NULL,
            created_at TEXT NOT NULL, PRIMARY KEY(round_id,proposal_id));
          CREATE TABLE IF NOT EXISTS accord_decision_handoffs(
            round_id TEXT NOT NULL, target_id TEXT NOT NULL, thread_id TEXT NOT NULL,
            PRIMARY KEY(round_id,target_id));
          CREATE TABLE IF NOT EXISTS accord_run_inputs(
            run_id TEXT PRIMARY KEY, manifest TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS accord_tool_calls(
            id TEXT PRIMARY KEY, run_id TEXT NOT NULL, call_id TEXT NOT NULL, name TEXT NOT NULL,
            resource_id TEXT NOT NULL DEFAULT '', resource_version INTEGER,
            status TEXT NOT NULL, result_chars INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
            UNIQUE(run_id,call_id));
          CREATE TABLE IF NOT EXISTS accord_thread_attachments(
            id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, message_id TEXT NOT NULL,
            owner_id TEXT NOT NULL, filename TEXT NOT NULL, content TEXT NOT NULL,
            mime_type TEXT NOT NULL, size INTEGER NOT NULL, digest TEXT NOT NULL,
            published_resource_id TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS accord_resources_scope ON accord_resources(scope,owner_id,round_id);
          CREATE INDEX IF NOT EXISTS accord_scopes_round ON accord_thread_scopes(round_id,purpose);
          CREATE INDEX IF NOT EXISTS accord_attachments_thread ON accord_thread_attachments(thread_id,message_id);
        """)
        if not db.execute('SELECT 1 FROM accord_schema_versions WHERE version=1').fetchone():
            for row in db.execute(
                'SELECT id,unit_id,title,body,created_at FROM artifacts'
            ).fetchall():
                db.execute(
                    'INSERT OR IGNORE INTO accord_resources(id,owner_id,kind,scope,created_at) VALUES(?,?,?,?,?)',
                    (row['id'], row['unit_id'], 'note', 'team', row['created_at']),
                )
                db.execute(
                    'INSERT OR IGNORE INTO accord_resource_versions(resource_id,version,title,body,digest,created_at) VALUES(?,1,?,?,?,?)',
                    (
                        row['id'],
                        row['title'],
                        row['body'],
                        hashlib.sha256(row['body'].encode()).hexdigest(),
                        row['created_at'],
                    ),
                )
            db.execute('INSERT INTO accord_schema_versions VALUES(1,?)', (store.now(),))
