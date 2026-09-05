import threading
from contextlib import asynccontextmanager

from accord_api.modules.agent_runs import generation as agent
from accord_api.modules.agent_runs.service import deliver_due, execute_run, finish
from accord_api.platform.db import database as store


def worker_loop(stop):
    workers = []
    flow_worker = None
    connection_worker = None
    from accord_api.modules.coordination import generation as flows
    from accord_api.modules.coordination.service import close_idle

    while not stop.is_set():
        from accord_api.modules.knowledge.index import synchronize

        with store.lock, store.connection() as db:
            synchronize(db, limit=100)
        deliver_due()
        close_idle()
        if connection_worker is None or not connection_worker.is_alive():
            from accord_api.modules.knowledge.connectors import next_due, sync_due

            due = next_due()
            if due:
                connection_worker = threading.Thread(
                    target=sync_due, args=(due['id'],), daemon=True
                )
                connection_worker.start()
        if flow_worker is None or not flow_worker.is_alive():
            pending = store.query_one(
                "SELECT id FROM accord_flows WHERE status IN ('queued','summarizing') ORDER BY created_at LIMIT 1"
            )
            if pending:
                flow_worker = threading.Thread(
                    target=flows.execute, args=(pending['id'],), daemon=True
                )
                flow_worker.start()
        workers = [worker for worker in workers if worker.is_alive()]
        if len(workers) < 2:
            # Only this coordinator dispatches work; the DB claim also guards explicit retries.
            for row in store.query(
                "SELECT id FROM accord_runs WHERE status='queued' ORDER BY created_at LIMIT ?",
                (2 - len(workers),),
            ):
                worker = threading.Thread(target=execute_run, args=(row['id'],), daemon=True)
                workers.append(worker)
                worker.start()
        stop.wait(0.3)


@asynccontextmanager
async def lifespan(app):
    from accord_api.modules.coordination.task_completion import recover

    store.execute(
        "UPDATE accord_flows SET status='error',error='服务重启中断了整理，请重试。' WHERE status='running'"
    )
    recover()
    store.execute(
        """UPDATE accord_content_connections SET status='error',error_code='interrupted',
        checked_at=?,updated_at=?,version=version+1 WHERE status='syncing'""",
        (store.now(), store.now()),
    )
    for row in store.query("SELECT id FROM accord_runs WHERE status='running'"):
        finish(
            row['id'],
            'error',
            agent.ModelError('interrupted', '服务重启中断了回答。已有内容已保存，可手动重试。'),
        )
    stop = threading.Event()
    worker = threading.Thread(target=worker_loop, args=(stop,), daemon=True)
    worker.start()
    try:
        yield
    finally:
        stop.set()
        store.execute(
            "UPDATE accord_flows SET status='error',error='服务正在重启，请稍后重试。' WHERE status='running'"
        )
        recover()
        worker.join(timeout=2)
        for row in store.query("SELECT id FROM accord_runs WHERE status='running'"):
            finish(
                row['id'], 'error', agent.ModelError('interrupted', '服务正在重启，请稍后重试。')
            )
