"""Derived search data. Source tables and their IDs remain the source of truth."""

from accord_api.platform.db import database as store


def initialize():
    with store.lock, store.connection() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS accord_index_queue(kind TEXT,id TEXT,PRIMARY KEY(kind,id));
        CREATE TABLE IF NOT EXISTS accord_content_chunks(
          id TEXT PRIMARY KEY, source_key TEXT NOT NULL, owner_id TEXT NOT NULL,
          source_kind TEXT NOT NULL, source_id TEXT NOT NULL, message_id TEXT NOT NULL,
          title TEXT NOT NULL, body TEXT NOT NULL, version INTEGER NOT NULL,
          offset INTEGER NOT NULL, digest TEXT NOT NULL, updated_at TEXT NOT NULL,
          active INTEGER NOT NULL DEFAULT 1);
        CREATE INDEX IF NOT EXISTS accord_chunks_owner ON accord_content_chunks(owner_id,active);
        CREATE INDEX IF NOT EXISTS accord_chunks_source ON accord_content_chunks(source_key);
        CREATE VIRTUAL TABLE IF NOT EXISTS accord_content_fts USING fts5(chunk_id UNINDEXED,terms);
        CREATE TABLE IF NOT EXISTS accord_content_imports(
          owner_id TEXT NOT NULL,filename TEXT NOT NULL,resource_id TEXT NOT NULL,
          digest TEXT NOT NULL,resource_version INTEGER NOT NULL,
          PRIMARY KEY(owner_id,filename));
        CREATE TABLE IF NOT EXISTS accord_content_connections(
          id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,provider TEXT NOT NULL,
          locator TEXT NOT NULL,external_id TEXT NOT NULL,title TEXT NOT NULL,
          resource_id TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,
          status TEXT NOT NULL DEFAULT 'ready',external_revision TEXT NOT NULL,
          digest TEXT NOT NULL,error_code TEXT NOT NULL DEFAULT '',
          checked_at TEXT NOT NULL,synced_at TEXT NOT NULL,created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,
          UNIQUE(owner_id,provider,external_id));
        CREATE INDEX IF NOT EXISTS accord_connections_due
          ON accord_content_connections(enabled,status,checked_at);
        CREATE TABLE IF NOT EXISTS accord_index_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TRIGGER IF NOT EXISTS accord_index_message_insert AFTER INSERT ON messages BEGIN
          INSERT OR IGNORE INTO accord_index_queue VALUES('message',new.id); END;
        CREATE TRIGGER IF NOT EXISTS accord_index_message_update AFTER UPDATE OF body,meta,sources ON messages BEGIN
          INSERT OR IGNORE INTO accord_index_queue VALUES('message',new.id); END;
        CREATE TRIGGER IF NOT EXISTS accord_index_message_delete AFTER DELETE ON messages BEGIN
          INSERT OR IGNORE INTO accord_index_queue VALUES('message',old.id); END;
        CREATE TRIGGER IF NOT EXISTS accord_index_thread_title AFTER UPDATE OF title ON accord_threads BEGIN
          INSERT OR IGNORE INTO accord_index_queue SELECT 'message',id FROM messages WHERE conversation_id=new.id; END;
        CREATE TRIGGER IF NOT EXISTS accord_index_resource_insert AFTER INSERT ON accord_resources BEGIN
          INSERT OR IGNORE INTO accord_index_queue VALUES('resource',new.id); END;
        CREATE TRIGGER IF NOT EXISTS accord_index_resource_update AFTER UPDATE ON accord_resources BEGIN
          INSERT OR IGNORE INTO accord_index_queue VALUES('resource',new.id); END;
        CREATE TRIGGER IF NOT EXISTS accord_index_resource_delete AFTER DELETE ON accord_resources BEGIN
          INSERT OR IGNORE INTO accord_index_queue VALUES('resource',old.id); END;
        """)
        if not db.execute("SELECT 1 FROM accord_index_meta WHERE key='backfill_v1'").fetchone():
            db.execute(
                "INSERT OR IGNORE INTO accord_index_queue SELECT 'resource',id FROM accord_resources"
            )
            db.execute("INSERT OR IGNORE INTO accord_index_queue SELECT 'message',id FROM messages")
            db.execute("INSERT INTO accord_index_meta VALUES('backfill_v1','queued')")
