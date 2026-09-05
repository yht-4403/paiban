from accord_api.platform.db import database as store


def initialize():
    with store.lock, store.connection():
        store.connection().executescript("""
          CREATE TABLE IF NOT EXISTS accord_sessions (
            digest TEXT PRIMARY KEY, unit_id TEXT NOT NULL, expires_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS accord_threads (
            id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, target_id TEXT NOT NULL,
            title TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'agent',
            delivery_at TEXT NOT NULL DEFAULT '', handoff_note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS accord_task_acl (
            task_id TEXT PRIMARY KEY, creator_id TEXT NOT NULL, thread_id TEXT NOT NULL UNIQUE);
          CREATE TABLE IF NOT EXISTS accord_operations (
            actor TEXT NOT NULL, operation_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
            status TEXT NOT NULL, result TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY(actor, operation_id));
        """)
