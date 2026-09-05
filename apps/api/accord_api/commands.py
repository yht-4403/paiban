"""Atomic user commands shared by workspace and collaboration workflows."""
import hashlib
import json

from fastapi import HTTPException
from pydantic import BaseModel, Field

from . import store


class Operation(BaseModel):
    operation_id: str = Field(min_length=8, max_length=100)


class VersionedOperation(Operation):
    expected_version: int = Field(ge=0)


def text(value):
    value = value.strip()
    if not value:
        raise HTTPException(422, '内容不能为空。')
    return value


def expect(actual, expected):
    if actual != expected:
        raise HTTPException(409, '内容已更新，请刷新后重试。你的输入已保留。')


def message(db, thread, kind, uid, body, sources=None, meta=None):
    mid = store.new_id('msg')
    db.execute('INSERT INTO messages(id,conversation_id,from_kind,from_unit,body,sources,meta,created_at) VALUES(?,?,?,?,?,?,?,?)',
        (mid, thread, kind, uid, body, json.dumps(sources or []), json.dumps(meta or {}), store.now()))
    return mid


def operate(uid, body, action, fn):
    fingerprint = hashlib.sha256((action + json.dumps(body.model_dump(), sort_keys=True)).encode()).hexdigest()
    with store._lock, store._conn:
        db = store._conn
        old = db.execute('SELECT * FROM accord_operations WHERE actor=? AND operation_id=?', (uid, body.operation_id)).fetchone()
        if old:
            if old['fingerprint'] != fingerprint:
                raise HTTPException(409, '请求标识已用于不同操作，请刷新后重试。')
            return json.loads(old['result'])
        result = fn(db)
        db.execute('INSERT INTO accord_operations(actor,operation_id,fingerprint,status,result) VALUES(?,?,?,?,?)',
            (uid, body.operation_id, fingerprint, 'done', json.dumps(result)))
        return result
