from accord_api.platform.db import database as store


def initialize():
    with store.lock, store.connection():
        store.connection().executescript("""
          CREATE TABLE IF NOT EXISTS accord_accounts (
            unit_id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
            role TEXT NOT NULL, created_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS accord_invites (
            digest TEXT PRIMARY KEY, created_by TEXT NOT NULL, expires_at TEXT NOT NULL,
            used_by TEXT NOT NULL DEFAULT '');
          CREATE TABLE IF NOT EXISTS accord_auth_attempts (
            scope TEXT PRIMARY KEY, count INTEGER NOT NULL, since TEXT NOT NULL);
        """)
