import hashlib
import json

from pydantic import BaseModel, Field

from accord_api.platform.db import database as store
from accord_api.platform.errors import DomainError


class Operation(BaseModel):
    operation_id: str = Field(min_length=8, max_length=100)


class VersionedOperation(Operation):
    expected_version: int = Field(ge=0)


def text(value):
    value = value.strip()
    if not value:
        raise DomainError(422, '内容不能为空。')
    return value


def expect(actual, expected):
    if actual != expected:
        raise DomainError(409, '内容已更新，请刷新后重试。你的输入已保留。')


def _fingerprint(action, payload):
    return hashlib.sha256((action + json.dumps(payload, sort_keys=True)).encode()).hexdigest()


def operate(uid, body, action, fn, legacy_payloads=None):
    fingerprint = _fingerprint(action, body.model_dump())
    accepted_fingerprints = {
        fingerprint,
        *(_fingerprint(action, payload) for payload in (legacy_payloads or [])),
    }
    with store.lock, store.connection():
        db = store.connection()
        old = db.execute(
            'SELECT * FROM accord_operations WHERE actor=? AND operation_id=?',
            (uid, body.operation_id),
        ).fetchone()
        if old:
            if old['fingerprint'] not in accepted_fingerprints:
                raise DomainError(409, '请求标识已用于不同操作，请刷新后重试。')
            return json.loads(old['result'])
        result = fn(db)
        db.execute(
            'INSERT INTO accord_operations(actor,operation_id,fingerprint,status,result) VALUES(?,?,?,?,?)',
            (uid, body.operation_id, fingerprint, 'done', json.dumps(result)),
        )
        return result
