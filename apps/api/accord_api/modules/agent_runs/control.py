import json

from accord_api.modules.agent_runs import generation as agent
from accord_api.modules.agent_runs import service as runtime
from accord_api.modules.permissions.policy import thread_for
from accord_api.platform.commands import Operation, operate
from accord_api.platform.errors import DomainError


def stop_run(*, rid: str, body: Operation, uid):
    def run(db):
        row = db.execute(
            'SELECT * FROM accord_runs WHERE id=? AND actor_id=?', (rid, uid)
        ).fetchone()
        if not row:
            raise DomainError(404, '生成记录不存在。')
        if row['status'] not in ('queued', 'running'):
            return {'status': row['status']}
        runtime.finish(rid, 'cancelled', agent.ModelError('cancelled', '已停止生成。'))
        return {'status': 'cancelled'}

    return operate(uid, body, 'stop:' + rid, run)


def retry_run(*, rid: str, body: Operation, uid):
    def run(db):
        row = db.execute(
            'SELECT * FROM accord_runs WHERE id=? AND actor_id=?', (rid, uid)
        ).fetchone()
        if not row:
            raise DomainError(404, '生成记录不存在。')
        thread = thread_for(uid, row['thread_id'], db)
        message = db.execute(
            'SELECT meta FROM messages WHERE id=?', (row['assistant_message_id'],)
        ).fetchone()
        latest = json.loads(message['meta']).get('run_id')
        if (
            row['status'] not in ('error', 'cancelled')
            or thread['status'] != 'agent'
            or latest != rid
        ):
            raise DomainError(409, '这条回答当前不能重试。')
        new_id = runtime.enqueue(
            db,
            row['thread_id'],
            uid,
            row['user_message_id'],
            row['assistant_message_id'],
            json.loads(row['source_ids']),
            previous_run_id=rid,
        )
        return {'run_id': new_id}

    return operate(uid, body, 'retry:' + rid, run)
