from accord_api.platform.db import database as store


def initialize():
    with store.lock, store.connection():
        store.connection().executescript("""
          CREATE TABLE IF NOT EXISTS accord_runs (
            id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, actor_id TEXT NOT NULL,
            user_message_id TEXT NOT NULL, assistant_message_id TEXT NOT NULL,
            status TEXT NOT NULL, model TEXT NOT NULL, source_ids TEXT NOT NULL,
            created_at TEXT NOT NULL, finished_at TEXT NOT NULL DEFAULT '',
            usage TEXT NOT NULL DEFAULT '{}', error_code TEXT NOT NULL DEFAULT '');
          CREATE INDEX IF NOT EXISTS accord_runs_queue ON accord_runs(status,created_at);
        """)
        columns = {
            row['name'] for row in store.connection().execute('PRAGMA table_info(accord_runs)')
        }
        for column in ('reasoning_effort', 'reasoning_content'):
            if column not in columns:
                store.connection().execute(
                    f"ALTER TABLE accord_runs ADD COLUMN {column} TEXT NOT NULL DEFAULT ''"
                )
