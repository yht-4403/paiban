"""Durable generation queue and scheduled delivery for a single API process."""
import json
import os
import threading
import time
from contextlib import asynccontextmanager

from fastapi import HTTPException

from . import agent, store


def initialize():
    with store._lock, store._conn:
        store._conn.executescript('''
          CREATE TABLE IF NOT EXISTS accord_runs (
            id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, actor_id TEXT NOT NULL,
            user_message_id TEXT NOT NULL, assistant_message_id TEXT NOT NULL,
            status TEXT NOT NULL, model TEXT NOT NULL, source_ids TEXT NOT NULL,
            created_at TEXT NOT NULL, finished_at TEXT NOT NULL DEFAULT '',
            usage TEXT NOT NULL DEFAULT '{}', error_code TEXT NOT NULL DEFAULT '');
          CREATE INDEX IF NOT EXISTS accord_runs_queue ON accord_runs(status,created_at);
        ''')


def deliver_due():
    store.execute("UPDATE accord_threads SET status='waiting',updated_at=? WHERE status='scheduled' AND delivery_at<=?", (store.now(), store.now()))


def active(db, tid):
    return db.execute("SELECT 1 FROM accord_runs WHERE thread_id=? AND status IN ('queued','running')", (tid,)).fetchone()


def enqueue(db, tid, uid, user_mid, assistant_mid, source_ids):
    if db.execute("SELECT 1 FROM accord_runs WHERE actor_id=? AND status IN ('queued','running')", (uid,)).fetchone():
        raise HTTPException(409, '上一条回答仍在生成，可以等待完成或先停止。')
    count = db.execute('SELECT count(*) FROM accord_runs WHERE actor_id=? AND created_at>=?', (uid, store.now()[:10])).fetchone()[0]
    if count >= int(os.environ.get('ACCORD_LLM_DAILY_LIMIT', '200')):
        raise HTTPException(429, '今天已达到工作空间设定的个人调用次数上限，请明天再试。')
    rid = store.new_id('run')
    model = agent.model_name()
    db.execute('INSERT INTO accord_runs(id,thread_id,actor_id,user_message_id,assistant_message_id,status,model,source_ids,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
        (rid, tid, uid, user_mid, assistant_mid, 'queued', model, json.dumps(source_ids), store.now()))
    meta = {'mode': 'model', 'status': 'queued', 'run_id': rid, 'model': model}
    db.execute('UPDATE messages SET body=?,sources=?,meta=? WHERE id=?', ('', '[]', json.dumps(meta), assistant_mid))
    return rid


def finish(rid, status, error=None, result=None):
    with store._lock, store._conn:
        db = store._conn
        row = db.execute('SELECT * FROM accord_runs WHERE id=?', (rid,)).fetchone()
        if not row or row['status'] not in ('queued', 'running'):
            return
        message = db.execute('SELECT * FROM messages WHERE id=?', (row['assistant_message_id'],)).fetchone()
        meta = json.loads(message['meta'])
        meta.update(status=status, mode='model' if status == 'done' else 'error')
        body = message['body']
        sources = json.loads(message['sources'])
        if error:
            meta.update(error=str(error), error_code=error.code)
        if result:
            body, sources = result['body'], result['sources']
            meta.update({key: result[key] for key in ('usage', 'model', 'finish_reason', 'duration_ms')})
        db.execute('UPDATE messages SET body=?,sources=?,meta=? WHERE id=?', (body, json.dumps(sources), json.dumps(meta), message['id']))
        db.execute('UPDATE accord_runs SET status=?,finished_at=?,usage=?,error_code=? WHERE id=?',
            (status, store.now(), json.dumps(result.get('usage', {}) if result else {}), error.code if error else '', rid))
        db.execute('UPDATE accord_threads SET updated_at=? WHERE id=?', (store.now(), row['thread_id']))


def execute_run(rid):
    # Claim before any paid network request. A restart fails running work instead of replaying it.
    with store._lock, store._conn:
        db = store._conn
        row = db.execute('SELECT * FROM accord_runs WHERE id=?', (rid,)).fetchone()
        if not row or row['status'] != 'queued':
            return
        db.execute("UPDATE accord_runs SET status='running' WHERE id=?", (rid,))
        thread = db.execute('SELECT * FROM accord_threads WHERE id=?', (row['thread_id'],)).fetchone()
        if not thread or thread['status'] != 'agent':
            finish(rid, 'error', agent.ModelError('state_changed', '协作状态已改变，未继续调用模型。'))
            return
        user_message = db.execute('SELECT rowid,* FROM messages WHERE id=?', (row['user_message_id'],)).fetchone()
        prior = db.execute('SELECT * FROM messages WHERE conversation_id=? AND rowid<? ORDER BY rowid DESC LIMIT 40', (row['thread_id'], user_message['rowid'])).fetchall()
        history = []
        for item in reversed(prior):
            if item['from_kind'] == 'human':
                history.append({'role': 'user', 'content': item['body']})
            elif item['from_kind'] == 'agent' and json.loads(item['meta']).get('status') == 'done':
                history.append({'role': 'assistant', 'content': item['body']})
        selected = json.loads(row['source_ids'])
        docs = [dict(d) for d in db.execute('SELECT id,title,body FROM artifacts ORDER BY created_at DESC').fetchall() if not selected or d['id'] in selected]
        target = db.execute('SELECT person_name FROM units WHERE id=?', (thread['target_id'],)).fetchone()
        meta = {'mode': 'model', 'status': 'running', 'run_id': rid, 'model': row['model']}
        db.execute('UPDATE messages SET meta=? WHERE id=?', (json.dumps(meta), row['assistant_message_id']))
    last_write = [0.0]

    def cancelled():
        current = store.query_one('SELECT status FROM accord_runs WHERE id=?', (rid,))
        return not current or current['status'] != 'running'

    def delta(content, sources):
        if time.monotonic() - last_write[0] < .15:
            return
        with store._lock, store._conn:
            db = store._conn
            current = db.execute('SELECT status FROM accord_runs WHERE id=?', (rid,)).fetchone()
            if current and current['status'] == 'running':
                db.execute('UPDATE messages SET body=?,sources=? WHERE id=?', (content, json.dumps(sources), row['assistant_message_id']))
        last_write[0] = time.monotonic()
    try:
        if cancelled():
            return
        result = agent.stream_answer(user_message['body'], docs, history, target['person_name'], thread['kind'] == 'peer',
            delta, cancelled, model=row['model'], explicit_sources=bool(selected))
        finish(rid, 'done', result=result)
    except agent.ModelError as error:
        finish(rid, 'cancelled' if error.code == 'cancelled' else 'error', error)
    except Exception:
        # Never serialize upstream exception objects, requests, credentials, or user content.
        finish(rid, 'error', agent.ModelError('internal', '回答生成遇到问题，消息已保存，请重试。'))


def usage_for(uid):
    rows = store.query('SELECT status,usage FROM accord_runs WHERE actor_id=? AND created_at>=?', (uid, store.now()[:10]))
    total = sum(json.loads(r['usage']).get('total_tokens', 0) for r in rows)
    return {'requests_today': len(rows), 'reported_tokens_today': total, 'daily_limit': int(os.environ.get('ACCORD_LLM_DAILY_LIMIT', '200'))}


def worker_loop(stop):
    workers = []
    while not stop.is_set():
        deliver_due()
        workers = [worker for worker in workers if worker.is_alive()]
        if len(workers) < 2:
            # Only this coordinator dispatches work; the DB claim also guards explicit retries.
            for row in store.query("SELECT id FROM accord_runs WHERE status='queued' ORDER BY created_at LIMIT ?", (2-len(workers),)):
                worker = threading.Thread(target=execute_run, args=(row['id'],), daemon=True)
                workers.append(worker)
                worker.start()
        stop.wait(.3)


@asynccontextmanager
async def lifespan(app):
    for row in store.query("SELECT id FROM accord_runs WHERE status='running'"):
        finish(row['id'], 'error', agent.ModelError('interrupted', '服务重启中断了回答。已有内容已保存，可手动重试。'))
    stop = threading.Event()
    worker = threading.Thread(target=worker_loop, args=(stop,), daemon=True)
    worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join(timeout=2)
        for row in store.query("SELECT id FROM accord_runs WHERE status='running'"):
            finish(row['id'], 'error', agent.ModelError('interrupted', '服务正在重启，请稍后重试。'))
