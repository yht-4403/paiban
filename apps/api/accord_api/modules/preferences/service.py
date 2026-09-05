from accord_api.modules.agent_runs import generation as agent
from accord_api.modules.preferences.schemas import ModelPreference, ReasoningPreference
from accord_api.platform.commands import operate
from accord_api.platform.errors import DomainError


def effort_for(db, uid):
    row = db.execute(
        'SELECT reasoning_effort FROM accord_model_preferences WHERE unit_id=?', (uid,)
    ).fetchone()
    return row['reasoning_effort'] if row else agent.default_reasoning_effort()


def model_for(db, uid):
    row = db.execute(
        'SELECT selected_model FROM accord_model_preferences WHERE unit_id=?', (uid,)
    ).fetchone()
    allowed = {model_id for model_id, _ in agent.model_options()}
    selected = row['selected_model'] if row else ''
    return selected if selected in allowed else agent.model_name()


def public_settings(db, uid):
    selected = model_for(db, uid)
    return {
        'label': agent.model_label(selected),
        'selected_model': selected,
        'model_options': [
            {'id': model_id, 'label': label} for model_id, label in agent.model_options()
        ],
        'reasoning_effort': effort_for(db, uid),
        'reasoning_options': list(agent.REASONING_EFFORTS) if agent.supports_reasoning() else [],
    }


def set_reasoning(*, body: ReasoningPreference, uid):
    if not agent.supports_reasoning():
        raise DomainError(409, '当前模型不支持调整思考强度。')

    def run(db):
        db.execute(
            """INSERT INTO accord_model_preferences(unit_id,reasoning_effort) VALUES(?,?)
            ON CONFLICT(unit_id) DO UPDATE SET reasoning_effort=excluded.reasoning_effort""",
            (uid, body.reasoning_effort),
        )
        return public_settings(db, uid)

    return operate(uid, body, 'reasoning_preference', run)


def set_model(*, body: ModelPreference, uid):
    if not agent.configured():
        raise DomainError(409, '模型尚未连接。')
    allowed = {model_id for model_id, _ in agent.model_options()}
    if body.model not in allowed:
        raise DomainError(422, '这个模型没有在当前工作空间启用。')

    def run(db):
        db.execute(
            """INSERT INTO accord_model_preferences(unit_id,reasoning_effort,selected_model)
            VALUES(?,?,?) ON CONFLICT(unit_id)
            DO UPDATE SET selected_model=excluded.selected_model""",
            (uid, effort_for(db, uid), body.model),
        )
        return public_settings(db, uid)

    return operate(uid, body, 'model_preference', run)
