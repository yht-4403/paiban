from accord_api.platform.db import database as store


def initialize():
    with store.lock, store.connection():
        store.connection().executescript("""
          CREATE TABLE IF NOT EXISTS accord_activity_preferences(
            owner_id TEXT PRIMARY KEY, automatic INTEGER NOT NULL DEFAULT 0,
            work_title INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS accord_presence(
            owner_id TEXT NOT NULL, client_id TEXT NOT NULL, surface TEXT NOT NULL,
            thread_id TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL, seen_at TEXT NOT NULL,
            PRIMARY KEY(owner_id,client_id));
          CREATE TABLE IF NOT EXISTS accord_task_priorities(
            task_id TEXT PRIMARY KEY, priority TEXT NOT NULL DEFAULT 'normal');
        """)
