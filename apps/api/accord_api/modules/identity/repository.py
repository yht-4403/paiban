import json
import sqlite3
from typing import Any, Optional

from accord_api.platform.db.database import query, query_one


def _loads(text: Optional[str], default: Any) -> Any:
    if not text:
        return default
    return json.loads(text)


def row_unit(row: sqlite3.Row) -> dict:
    return {
        'id': row['id'],
        'person_name': row['person_name'],
        'agent_name': row['agent_name'],
        'window': row['window'],
        'tags': _loads(row['tags'], []),
        'memory': _loads(row['memory'], []),
        'workflows': _loads(row['workflows'], []),
        'report_times': _loads(
            row['report_times'] if 'report_times' in row.keys() else None, ['11:30', '16:30']
        )
        or ['11:30', '16:30'],
        'created_at': row['created_at'],
    }


def list_units() -> list[dict]:
    return [row_unit(r) for r in query('SELECT * FROM units ORDER BY created_at')]


def get_unit(unit_id: str) -> Optional[dict]:
    row = query_one('SELECT * FROM units WHERE id=?', (unit_id,))
    return row_unit(row) if row else None
