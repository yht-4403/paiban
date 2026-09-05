from accord_api.platform.db import database as store
from accord_api.platform.db.migrations.legacy_files import export_missing_pool_files


def init() -> None:
    with store.lock:
        store.connection().executescript(
            """
            CREATE TABLE IF NOT EXISTS units (
                id TEXT PRIMARY KEY,
                person_name TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                window TEXT NOT NULL DEFAULT 'open',
                tags TEXT NOT NULL DEFAULT '[]',
                memory TEXT NOT NULL DEFAULT '[]',
                workflows TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                a_id TEXT NOT NULL,
                b_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (a_id, b_id)
            );
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                from_kind TEXT NOT NULL,
                from_unit TEXT NOT NULL,
                body TEXT NOT NULL,
                sources TEXT NOT NULL DEFAULT '[]',
                parent_id TEXT NOT NULL DEFAULT '',
                meta TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS handoffs (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                message_id TEXT NOT NULL DEFAULT '',
                from_unit TEXT NOT NULL,
                to_unit TEXT NOT NULL,
                mode TEXT NOT NULL,
                deadline TEXT NOT NULL DEFAULT '',
                deliver_at TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                delivered_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                assignee_id TEXT,
                assign_reason TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS routes (
                id TEXT PRIMARY KEY,
                from_unit TEXT NOT NULL,
                to_unit TEXT NOT NULL,
                question TEXT NOT NULL,
                urgency TEXT NOT NULL DEFAULT 'low',
                status TEXT NOT NULL,
                answer TEXT NOT NULL DEFAULT '',
                sources TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS decisions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                context TEXT NOT NULL DEFAULT '',
                options TEXT NOT NULL DEFAULT '[]',
                evidence TEXT NOT NULL DEFAULT '',
                fail_if TEXT NOT NULL DEFAULT '',
                required_ids TEXT NOT NULL DEFAULT '[]',
                fyi_ids TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'draft',
                content_hash TEXT NOT NULL DEFAULT '',
                locked_by TEXT NOT NULL DEFAULT '',
                created_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                locked_at TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS scratch (
                id TEXT PRIMARY KEY,
                unit_id TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL,
                path TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS meeting_msgs (
                id TEXT PRIMARY KEY,
                decision_id TEXT NOT NULL,
                from_unit TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL DEFAULT '',
                unit_id TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                unit_id TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',
                source TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS project_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS duty_log (
                id TEXT PRIMARY KEY,
                unit_id TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                sources TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );
            """
        )

        def _col(table: str, name: str, spec: str) -> None:
            existing = [
                r[1] for r in store.connection().execute(f'PRAGMA table_info({table})').fetchall()
            ]
            if name not in existing:
                store.connection().execute(f'ALTER TABLE {table} ADD COLUMN {name} {spec}')

        _col('units', 'report_times', 'TEXT NOT NULL DEFAULT \'["11:30","16:30"]\'')
        _col('tasks', 'module', "TEXT NOT NULL DEFAULT ''")
        _col('tasks', 'how_to', "TEXT NOT NULL DEFAULT ''")
        _col('tasks', 'artifact', "TEXT NOT NULL DEFAULT ''")
        _col('tasks', 'await_note', "TEXT NOT NULL DEFAULT ''")
        _col('decisions', 'acks', "TEXT NOT NULL DEFAULT '[]'")
        _col('decisions', 'missing_ids', "TEXT NOT NULL DEFAULT '[]'")
        _col('decisions', 'convened_ids', "TEXT NOT NULL DEFAULT '[]'")
        _col('decisions', 'pushed_at', "TEXT NOT NULL DEFAULT ''")
        _col('decisions', 'attendee_ids', "TEXT NOT NULL DEFAULT '[]'")
        _col('decisions', 'conclusion', "TEXT NOT NULL DEFAULT ''")
        _col('decisions', 'wrap_todos', "TEXT NOT NULL DEFAULT '[]'")
        _col('decisions', 'wrap_memory', "TEXT NOT NULL DEFAULT ''")
        _col('decisions', 'wrap_title', "TEXT NOT NULL DEFAULT ''")
        _col('tasks', 'remind_at', "TEXT NOT NULL DEFAULT ''")
        _col('conversations', 'channel', "TEXT NOT NULL DEFAULT 'agent'")
        _col('conversations', 'channel_handoff', "TEXT NOT NULL DEFAULT ''")
        _col('conversations', 'human_for', "TEXT NOT NULL DEFAULT ''")
        _col('artifacts', 'path', "TEXT NOT NULL DEFAULT ''")
        _col('artifacts', 'author', "TEXT NOT NULL DEFAULT ''")
        _col('artifacts', 'kind', "TEXT NOT NULL DEFAULT 'file'")
        store.connection().commit()
    export_missing_pool_files()
