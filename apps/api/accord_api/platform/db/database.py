"""Single-process SQLite connection and transaction lock; no business queries."""

import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from accord_api.platform.config import data_root, database_path

lock = threading.RLock()
_connection = None


def connection() -> sqlite3.Connection:
    global _connection
    with lock:
        if _connection is None:
            root = data_root()
            root.mkdir(parents=True, exist_ok=True)
            root.chmod(0o700)
            path = database_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            _connection = sqlite3.connect(str(path), check_same_thread=False)
            path.chmod(0o600)
            _connection.row_factory = sqlite3.Row
            _connection.execute('PRAGMA journal_mode=WAL')
            _connection.execute('PRAGMA foreign_keys=ON')
        return _connection


def execute(sql, params=()):
    with lock, connection() as db:
        return db.execute(sql, params)


def query(sql, params=()):
    with lock:
        return connection().execute(sql, params).fetchall()


def query_one(sql, params=()):
    with lock:
        return connection().execute(sql, params).fetchone()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f'{prefix}_{uuid.uuid4().hex[:10]}'
