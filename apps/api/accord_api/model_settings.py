"""Authenticated personal model preferences; credentials remain server-only."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from . import agent, store
from .auth import principal
from .commands import Operation, operate

router = APIRouter(prefix='/api/profile')


def initialize():
    store.execute('''CREATE TABLE IF NOT EXISTS accord_model_preferences (
        unit_id TEXT PRIMARY KEY, reasoning_effort TEXT NOT NULL)''')


def effort_for(db, uid):
    row = db.execute('SELECT reasoning_effort FROM accord_model_preferences WHERE unit_id=?', (uid,)).fetchone()
    return row['reasoning_effort'] if row else agent.default_reasoning_effort()


def public_settings(db, uid):
    return {'reasoning_effort': effort_for(db, uid),
            'reasoning_options': list(agent.REASONING_EFFORTS) if agent.supports_reasoning() else []}


class ReasoningPreference(Operation):
    reasoning_effort: Literal['low', 'high', 'max']


@router.post('/reasoning')
def set_reasoning(body: ReasoningPreference, uid=Depends(principal)):
    if not agent.supports_reasoning():
        raise HTTPException(409, '当前模型不支持调整思考强度。')

    def run(db):
        db.execute('''INSERT INTO accord_model_preferences VALUES(?,?)
            ON CONFLICT(unit_id) DO UPDATE SET reasoning_effort=excluded.reasoning_effort''',
            (uid, body.reasoning_effort))
        return public_settings(db, uid)
    return operate(uid, body, 'reasoning_preference', run)
