import json
import sqlite3
from typing import Any, Optional

from accord_api.platform.db import database as store
from accord_api.platform.db.database import query, query_one


def _loads(text: Optional[str], default: Any) -> Any:
    if not text:
        return default
    return json.loads(text)


def row_task(row: sqlite3.Row) -> dict:
    return {
        'id': row['id'],
        'title': row['title'],
        'detail': row['detail'],
        'status': row['status'],
        'assignee_id': row['assignee_id'],
        'assign_reason': row['assign_reason'],
        'tags': _loads(row['tags'], []),
        'module': row['module'] if 'module' in row.keys() else '',
        'how_to': row['how_to'] if 'how_to' in row.keys() else '',
        'artifact': row['artifact'] if 'artifact' in row.keys() else '',
        'await_note': row['await_note'] if 'await_note' in row.keys() else '',
        'remind_at': row['remind_at'] if 'remind_at' in row.keys() else '',
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
    }


def list_tasks() -> list[dict]:
    return [row_task(r) for r in query('SELECT * FROM tasks ORDER BY created_at DESC')]


def get_task(task_id: str) -> Optional[dict]:
    row = query_one('SELECT * FROM tasks WHERE id=?', (task_id,))
    return row_task(row) if row else None


def row_msg(row: sqlite3.Row, uid=None, db=None) -> dict:
    result = {
        'id': row['id'],
        'conversation_id': row['conversation_id'],
        'from_kind': row['from_kind'],
        'from_unit': row['from_unit'],
        'body': row['body'],
        'sources': _loads(row['sources'], []),
        'parent_id': row['parent_id'],
        'meta': _loads(row['meta'], {}),
        'created_at': row['created_at'],
    }
    if uid:
        from accord_api.modules.knowledge.retrieval import check_message
        from accord_api.platform.errors import DomainError

        try:
            check_message(db, row, [uid])
            if result['meta'].get('run_id'):
                from accord_api.modules.knowledge import person_context

                saved = db.execute(
                    'SELECT manifest FROM accord_run_inputs WHERE run_id=?',
                    (result['meta']['run_id'],),
                ).fetchone()
                if saved:
                    person_context.validate(
                        db,
                        json.loads(saved['manifest']).get('context_sources', []),
                        [uid],
                        strict=False,
                    )
        except DomainError:
            result.update(body='引用内容已收回。', sources=[], meta={'context_unavailable': True})
    return result


def message(db, thread, kind, uid, body, sources=None, meta=None):
    mid = store.new_id('msg')
    db.execute(
        'INSERT INTO messages(id,conversation_id,from_kind,from_unit,body,sources,meta,created_at) VALUES(?,?,?,?,?,?,?,?)',
        (
            mid,
            thread,
            kind,
            uid,
            body,
            json.dumps(sources or []),
            json.dumps(meta or {}),
            store.now(),
        ),
    )
    return mid
