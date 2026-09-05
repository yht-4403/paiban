"""Accord workspace API: real accounts, explicit permissions and persisted model runs."""
import json
import os
from datetime import datetime, timezone
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from urllib.parse import urlsplit
from pydantic import BaseModel, Field

from . import access, agent, auth, context, runtime, schema, store, workspace, topics, activity, chats
from .auth import principal
from . import model_settings
from .access import thread_for
from .commands import Operation, message as _message, operate, text

app = FastAPI(title='Accord', docs_url=None, redoc_url=None, lifespan=runtime.lifespan)
store.init()


def initialize():
    with store._lock, store._conn:
        store._conn.executescript('''
          CREATE TABLE IF NOT EXISTS accord_sessions (
            digest TEXT PRIMARY KEY, unit_id TEXT NOT NULL, expires_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS accord_threads (
            id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, target_id TEXT NOT NULL,
            title TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'agent',
            delivery_at TEXT NOT NULL DEFAULT '', handoff_note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS accord_task_acl (
            task_id TEXT PRIMARY KEY, creator_id TEXT NOT NULL, thread_id TEXT NOT NULL UNIQUE);
          CREATE TABLE IF NOT EXISTS accord_operations (
            actor TEXT NOT NULL, operation_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
            status TEXT NOT NULL, result TEXT NOT NULL DEFAULT '{}',
            PRIMARY KEY(actor, operation_id));
        ''')
    auth.initialize()
    runtime.initialize()
    model_settings.initialize()
    schema.initialize()
    activity.initialize()
    if store.query_one("SELECT 1 FROM project_state WHERE key='accord_seed_v1'"):
        raise RuntimeError('请为真实工作空间设置独立的 ACCORD_DATA_DIR，旧参考数据保留原位。')




initialize()


app.include_router(auth.router)
app.include_router(workspace.router)
app.include_router(model_settings.router)
app.include_router(topics.router)
app.include_router(activity.router)
app.include_router(chats.router)

@app.exception_handler(RequestValidationError)
async def validation_error(request, error):
    return JSONResponse({'detail': '输入内容不完整或超出长度限制，请检查表单。'}, status_code=422)



@app.middleware('http')
async def same_origin(request: Request, call_next):
    origin = request.headers.get('origin')
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin:
        allowed = {request.headers.get('host', '')}
        configured_origin = os.environ.get('ACCORD_PUBLIC_ORIGIN', '')
        if configured_origin:
            allowed.add(urlsplit(configured_origin).netloc)
        # The local Vite development proxy preserves the originating Host header.
        if urlsplit(origin).netloc not in allowed:
            return JSONResponse({'detail': '请求来源不匹配，请从工作空间页面操作。'}, status_code=403)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response




class NewThread(Operation):
    target_id: str
    title: str = Field(default='新的协作', max_length=100)
    folder_id: str = Field(default='', max_length=100)
    source_ids: list[str] = Field(default_factory=list, max_length=20)


class Message(Operation):
    body: str = Field(min_length=1, max_length=8000)
    source_ids: list[str] = Field(default_factory=list, max_length=10)


class Handoff(Operation):
    mode: Literal['now', 'deadline'] = 'now'
    deadline: str = ''
    note: str = Field(default='', max_length=1000)


class Confirmation(Operation):
    conclusion: str = Field(min_length=1, max_length=4000)
    task_title: str = Field(min_length=1, max_length=160)
    assignee_id: str


class TaskStatus(Operation):
    status: Literal['open', 'done']


class SharedDocument(Operation):
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=16000)








def public_units():
    return [{k: u[k] for k in ('id','person_name','agent_name','window','tags')} for u in store.list_units()]


def documents():
    return [dict(r) for r in store.query('SELECT id,unit_id,title,body,created_at,author FROM artifacts ORDER BY created_at DESC')]


@app.get('/api/health')
def health():
    return {'status': 'ok'}


@app.get('/api/state')
def state(uid=Depends(principal)):
    with store._lock:
        db=store._conn
        threads=[]
        for row in db.execute('SELECT id FROM accord_threads WHERE owner_id=? OR target_id=? ORDER BY updated_at DESC', (uid,uid)).fetchall():
            try: threads.append(thread_for(uid,row['id'],db))
            except HTTPException: pass
        tasks = [dict(r) for r in db.execute('''SELECT t.*,a.creator_id,a.thread_id FROM tasks t JOIN accord_task_acl a ON a.task_id=t.id
            WHERE a.creator_id=? OR t.assignee_id=? ORDER BY t.created_at DESC''', (uid,uid)) if any(t['id']==r['thread_id'] for t in threads)]
        return {'me':uid,'members':[{**member,'activity':activity.visible(db,uid,member['id'])} for member in public_units()],'threads':threads,'tasks':[{**task,'priority':activity.task_priority(db,task['id'])} for task in tasks],'documents':context.available(db,uid),
            'folders':workspace.folders(db,uid),'topics':topics.list_rounds(db,uid),
            'model': {'mode':'model' if agent.configured() else 'unavailable','label':agent.model_name() if agent.configured() else '模型未连接', **runtime.usage_for(uid), **model_settings.public_settings(db, uid)},
            'activity_preferences':activity.preferences(db,uid),'account':auth.account(uid),'project':{'name':auth.workspace_name()}}


@app.post('/api/threads')
def new_thread(body: NewThread, uid=Depends(principal)):
    if not store.get_unit(body.target_id):
        raise HTTPException(404, '成员不存在。')
    def run(db):
        if body.folder_id:
            workspace.folder_for(db, uid, body.folder_id)
        tid = store.new_id('thread')
        now = store.now()
        db.execute('INSERT INTO accord_threads(id,owner_id,target_id,title,kind,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
            (tid,uid,body.target_id,text(body.title),'workspace' if body.target_id==uid else 'peer',now,now))
        if body.folder_id:
            db.execute('INSERT INTO accord_placements VALUES(?,?,?,1)', (uid,tid,body.folder_id))
        if body.source_ids:
            current=thread_for(uid,tid,db)
            for resource_id in body.source_ids:
                resource=access.resource_for(db,uid,resource_id)
                if not access.compatible(db,current,resource):
                    raise HTTPException(403,'这份资料不适用于当前协作范围。')
            context.put_binding(db,uid,'thread',tid,body.source_ids,[],1)
        return {'id':tid}
    return operate(uid,body,'create_thread',run)


@app.get('/api/threads/{tid}')
def thread(tid: str, person_history: bool=False, uid=Depends(principal)):
    with store._lock:
        db=store._conn
        row=thread_for(uid,tid,db)
        segments=chats.pair_threads(db,uid,row['target_id'] if row['owner_id']==uid else row['owner_id']) if person_history and row['kind']=='peer' else [row]
        messages=[]; tool_calls=[]
        for segment in segments:
            messages.extend(store.row_msg(r) for r in db.execute('SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at,rowid',(segment['id'],)))
            tool_calls.extend(dict(r) for r in db.execute('SELECT c.*,r.assistant_message_id FROM accord_tool_calls c JOIN accord_runs r ON r.id=c.run_id WHERE r.thread_id=? ORDER BY c.created_at,c.rowid',(segment['id'],)))
        inputs = {r['run_id']:json.loads(r['manifest']) for r in db.execute('''SELECT i.* FROM accord_run_inputs i JOIN accord_runs r ON r.id=i.run_id
            WHERE r.thread_id=? AND r.status IN ('queued','running')''', (tid,))}
        return {'thread':row,'messages':messages,'tool_calls':tool_calls,'segments':segments,
            'context':{**context.effective(db,uid,row),'available':context.available(db,uid,row,False)},
            'active_context': [{k:m[k] for k in ('resources','roots','binding_version','folder_id','folder_version') if k in m} for m in inputs.values()]}


@app.post('/api/threads/{tid}/messages')
def send_message(tid: str, body: Message, uid=Depends(principal)):
    content = text(body.body)
    def run(db):
        current = thread_for(uid, tid, db)
        if current['status'] == 'scheduled':
            raise HTTPException(409, '这条协作尚未送达，草稿可以保留，送达后继续发送。')
        for resource_id in body.source_ids:
            resource = access.resource_for(db, uid, resource_id)
            if not access.compatible(db, current, resource):
                raise HTTPException(404, '引用资料不存在或不可共享。')
        if runtime.active(db, tid):
            raise HTTPException(409, '回答仍在生成，可以先停止。')
        if body.source_ids and current['status'] == 'agent':
            current_binding = context.binding(db, uid, 'thread', tid)
            context.put_binding(db, uid, 'thread', tid, current_binding['included'] + body.source_ids,
                [rid for rid in current_binding['excluded'] if rid not in body.source_ids], current_binding['version']+1)
        if uid == current['target_id'] and current['status'] == 'waiting':
            _message(db, tid, 'system', uid, '本人开始回复，Agent 暂停代答。')
        mid = _message(db, tid, 'human', uid, content, body.source_ids)
        rid = None
        if current['status'] == 'agent':
            assistant_mid = _message(db, tid, 'agent', current['target_id'], '')
            rid = runtime.enqueue(db, tid, uid, mid, assistant_mid, body.source_ids)
        if uid == current['target_id'] and current['status'] == 'waiting':
            db.execute("UPDATE accord_threads SET status='human' WHERE id=?", (tid,))
        title = content[:40] if current['title'] == '新的协作' else current['title']
        db.execute('UPDATE accord_threads SET title=?,updated_at=? WHERE id=?', (title, store.now(), tid))
        return {'id': mid, 'run_id': rid}
    return operate(uid, body, 'message:' + tid, run)


@app.post('/api/runs/{rid}/stop')
def stop_run(rid: str, body: Operation, uid=Depends(principal)):
    def run(db):
        row = db.execute('SELECT * FROM accord_runs WHERE id=? AND actor_id=?', (rid, uid)).fetchone()
        if not row:
            raise HTTPException(404, '生成记录不存在。')
        if row['status'] not in ('queued', 'running'):
            return {'status': row['status']}
        runtime.finish(rid, 'cancelled', agent.ModelError('cancelled', '已停止生成。'))
        return {'status': 'cancelled'}
    return operate(uid, body, 'stop:' + rid, run)


@app.post('/api/runs/{rid}/retry')
def retry_run(rid: str, body: Operation, uid=Depends(principal)):
    def run(db):
        row = db.execute('SELECT * FROM accord_runs WHERE id=? AND actor_id=?', (rid, uid)).fetchone()
        if not row:
            raise HTTPException(404, '生成记录不存在。')
        thread = thread_for(uid, row['thread_id'], db)
        message = db.execute('SELECT meta FROM messages WHERE id=?', (row['assistant_message_id'],)).fetchone()
        latest = json.loads(message['meta']).get('run_id')
        if row['status'] not in ('error', 'cancelled') or thread['status'] != 'agent' or latest != rid:
            raise HTTPException(409, '这条回答当前不能重试。')
        new_id = runtime.enqueue(db, row['thread_id'], uid, row['user_message_id'], row['assistant_message_id'], json.loads(row['source_ids']), previous_run_id=rid)
        return {'run_id': new_id}
    return operate(uid, body, 'retry:' + rid, run)


@app.post('/api/threads/{tid}/handoff')
def handoff(tid: str, body: Handoff, uid=Depends(principal)):
    def run(db):
        row=thread_for(uid,tid,db)
        if row['purpose'] != 'ordinary':
            raise HTTPException(403, '请使用课题内的提交或交接操作。')
        if row['owner_id']!=uid or row['kind']!='peer':
            raise HTTPException(403,'只有发起人可以找对方本人。')
        if row['status']!='agent':
            raise HTTPException(409,'这条请求已经提交给本人。')
        if runtime.active(db, tid):
            raise HTTPException(409, '请等待回答完成，或先停止生成再找本人。')
        if not db.execute('SELECT 1 FROM messages WHERE conversation_id=?',(tid,)).fetchone():
            raise HTTPException(422,'先说明需要对方处理的事情。')
        delivery=store.now()
        if body.mode=='deadline':
            try:
                when=datetime.fromisoformat(body.deadline.replace('Z','+00:00'))
                if when.tzinfo is None:
                    raise ValueError()
                if when<=datetime.now(timezone.utc):
                    raise ValueError()
                delivery=when.astimezone(timezone.utc).isoformat()
            except ValueError:
                raise HTTPException(422,'请选择未来的送达时间，时间必须包含时区。')
        status='waiting' if body.mode=='now' else 'scheduled'
        db.execute('UPDATE accord_threads SET status=?,delivery_at=?,handoff_note=?,updated_at=? WHERE id=?',
            (status,delivery,body.note.strip(),store.now(),tid))
        _message(db,tid,'system',uid,'已请本人处理。' if status=='waiting' else '已安排在指定时间送达本人。')
        return {'status':status,'delivery_at':delivery}
    return operate(uid,body,'handoff:'+tid,run)


@app.post('/api/threads/{tid}/confirm')
def confirm(tid: str, body: Confirmation, uid=Depends(principal)):
    conclusion=text(body.conclusion)
    title=text(body.task_title)
    def run(db):
        row=thread_for(uid,tid,db)
        if uid!=row['target_id'] or row['kind']!='peer':
            raise HTTPException(403,'需要被找的本人确认。')
        if row['status'] not in ('waiting','human'):
            raise HTTPException(409,'这条协作当前不能确认。')
        if body.assignee_id!=uid:
            raise HTTPException(422,'请由任务负责人本人确认承担。')
        task_id=store.new_id('task')
        now=store.now()
        db.execute('INSERT INTO tasks(id,title,detail,status,assignee_id,assign_reason,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
            (task_id,title,conclusion,'open',uid,'本人确认',now,now))
        db.execute('INSERT INTO accord_task_acl(task_id,creator_id,thread_id) VALUES(?,?,?)',(task_id,row['owner_id'],tid))
        _message(db,tid,'human',uid,conclusion)
        _message(db,tid,'system',uid,'本人已确认，并加入待办：'+title,meta={'task_id':task_id})
        db.execute("UPDATE accord_threads SET status='resolved',updated_at=? WHERE id=?",(now,tid))
        return {'task_id':task_id}
    return operate(uid,body,'confirm:'+tid,run)


@app.post('/api/tasks/{task_id}/status')
def task_status(task_id: str, body: TaskStatus, uid=Depends(principal)):
    def run(db):
        task=db.execute('SELECT * FROM tasks WHERE id=?',(task_id,)).fetchone()
        if not task or task['assignee_id']!=uid:
            raise HTTPException(404,'待办不存在或需要负责人操作。')
        db.execute('UPDATE tasks SET status=?,updated_at=? WHERE id=?',(body.status,store.now(),task_id))
        return {'status':body.status}
    return operate(uid,body,'task_status:'+task_id,run)


@app.post('/api/documents')
def publish(body: SharedDocument, uid=Depends(principal)):
    title=text(body.title)
    content=text(body.body)
    def run(db):
        aid=context.create_resource(db, uid, title, content, scope='team')
        db.execute('INSERT INTO artifacts(id,unit_id,title,body,created_at,kind,author) VALUES(?,?,?,?,?,?,?)',
            (aid,uid,title,content,store.now(),'note',uid))
        return {'id':aid}
    return operate(uid,body,'publish',run)


class Availability(Operation):
    window: Literal['open', 'closed']


@app.post('/api/profile/availability')
def availability(body: Availability, uid=Depends(principal)):
    def run(db):
        db.execute('UPDATE units SET window=? WHERE id=?', (body.window, uid))
        return {'window': body.window}
    return operate(uid, body, 'availability', run)
