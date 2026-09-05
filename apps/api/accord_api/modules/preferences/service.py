from accord_api.modules.agent_runs import generation as agent
from accord_api.modules.preferences.schemas import ReasoningPreference
from accord_api.platform.commands import operate
from accord_api.platform.errors import DomainError


def effort_for(db, uid):
    row = db.execute(
        'SELECT reasoning_effort FROM accord_model_preferences WHERE unit_id=?', (uid,)
    ).fetchone()
    return row['reasoning_effort'] if row else agent.default_reasoning_effort()


def public_settings(db, uid):
    return {
        'reasoning_effort': effort_for(db, uid),
        'reasoning_options': list(agent.REASONING_EFFORTS) if agent.supports_reasoning() else [],
    }


def set_reasoning(*, body: ReasoningPreference, uid):
    if not agent.supports_reasoning():
        raise DomainError(409, '当前模型不支持调整思考强度。')

    def run(db):
        db.execute(
            """INSERT INTO accord_model_preferences VALUES(?,?)
            ON CONFLICT(unit_id) DO UPDATE SET reasoning_effort=excluded.reasoning_effort""",
            (uid, body.reasoning_effort),
        )
        return public_settings(db, uid)

    return operate(uid, body, 'reasoning_preference', run)
