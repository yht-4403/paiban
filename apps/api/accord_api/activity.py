"""Self-controlled Accord activity; never inspect another app or private message body."""
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import access, store
from .auth import principal
from .commands import Operation, VersionedOperation, expect, operate

router = APIRouter(prefix='/api')


def initialize():
    with store._lock, store._conn:
        store._conn.executescript('''
          CREATE TABLE IF NOT EXISTS accord_activity_preferences(
            owner_id TEXT PRIMARY KEY, automatic INTEGER NOT NULL DEFAULT 0,
            work_title INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS accord_presence(
            owner_id TEXT NOT NULL, client_id TEXT NOT NULL, surface TEXT NOT NULL,
            thread_id TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL, seen_at TEXT NOT NULL,
            PRIMARY KEY(owner_id,client_id));
          CREATE TABLE IF NOT EXISTS accord_task_priorities(
            task_id TEXT PRIMARY KEY, priority TEXT NOT NULL DEFAULT 'normal');
        ''')


def preferences(db, uid):
    row=db.execute('SELECT * FROM accord_activity_preferences WHERE owner_id=?',(uid,)).fetchone()
    return {'automatic':bool(row['automatic']), 'work_title':bool(row['work_title']), 'version':row['version']} if row else {'automatic':False,'work_title':False,'version':0}


class Preference(VersionedOperation):
    automatic: bool
    work_title: bool = False


@router.post('/profile/activity')
def preference(body:Preference, uid=Depends(principal)):
    def run(db):
        current=preferences(db,uid);expect(current['version'],body.expected_version)
        db.execute('''INSERT INTO accord_activity_preferences VALUES(?,?,?,?) ON CONFLICT(owner_id)
          DO UPDATE SET automatic=excluded.automatic,work_title=excluded.work_title,version=excluded.version''',
          (uid,int(body.automatic),int(body.automatic and body.work_title),current['version']+1))
        if not body.automatic:db.execute('DELETE FROM accord_presence WHERE owner_id=?',(uid,))
        return preferences(db,uid)
    return operate(uid,body,'activity:preference',run)


class Heartbeat(BaseModel):
    client_id: str=Field(min_length=8,max_length=100)
    surface: Literal['work','chat']
    thread_id: str=Field(default='',max_length=100)
    active: bool=True


@router.post('/presence')
def heartbeat(body:Heartbeat, uid=Depends(principal)):
    with store._lock,store._conn:
        db=store._conn
        if not preferences(db,uid)['automatic']:return {'recorded':False}
        if body.thread_id:access.thread_for(uid,body.thread_id,db)
        cutoff=(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()
        db.execute('DELETE FROM accord_presence WHERE owner_id=? AND seen_at<?',(uid,cutoff))
        if not db.execute('SELECT 1 FROM accord_presence WHERE owner_id=? AND client_id=?',(uid,body.client_id)).fetchone() and db.execute('SELECT count(*) FROM accord_presence WHERE owner_id=?',(uid,)).fetchone()[0]>=16:
            raise HTTPException(429,'当前活跃页面过多，请关闭不用的页面。')
        db.execute('''INSERT INTO accord_presence VALUES(?,?,?,?,?,?) ON CONFLICT(owner_id,client_id)
          DO UPDATE SET surface=excluded.surface,thread_id=excluded.thread_id,active=excluded.active,seen_at=excluded.seen_at''',
          (uid,body.client_id,body.surface,body.thread_id,int(body.active),store.now()))
        return {'recorded':True}


def task_priority(db,task_id):
    row=db.execute('SELECT priority FROM accord_task_priorities WHERE task_id=?',(task_id,)).fetchone()
    return row['priority'] if row else 'normal'


class Priority(Operation):
    priority:Literal['high','normal','low']


@router.post('/tasks/{tid}/priority')
def priority(tid:str,body:Priority,uid=Depends(principal)):
    def run(db):
        if not db.execute('SELECT 1 FROM tasks WHERE id=? AND assignee_id=?',(tid,uid)).fetchone():
            raise HTTPException(404,'待办不存在或需要负责人操作。')
        db.execute('''INSERT INTO accord_task_priorities VALUES(?,?) ON CONFLICT(task_id) DO UPDATE SET priority=excluded.priority''',(tid,body.priority))
        return {'priority':body.priority}
    return operate(uid,body,'task:priority:'+tid,run)


def visible(db,viewer,subject):
    unit=db.execute('SELECT u.* FROM units u JOIN accord_accounts a ON a.unit_id=u.id WHERE u.id=?',(subject,)).fetchone()
    if not unit:raise HTTPException(404,'成员不存在。')
    pref=preferences(db,subject)
    cutoff=(datetime.now(timezone.utc)-timedelta(seconds=75)).isoformat()
    presence=db.execute('SELECT * FROM accord_presence WHERE owner_id=? AND active=1 AND seen_at>? ORDER BY seen_at DESC LIMIT 1',(subject,cutoff)).fetchone() if pref['automatic'] else None
    label='专注中' if unit['window']=='closed' else '可协作'
    result={'label':label,'availability':label,'source':'本人设置','seen_at':None,'agent_working':False,'work':None,'meeting':'未接入会议状态','shared_tasks':[],'permission_version':pref['version']}
    if pref['automatic']:
        result.update(label=('在 Accord 聊天' if presence['surface']=='chat' else '在 Accord 工作') if presence and unit['window']!='closed' else label,
          source='Accord' if presence else '本人设置',seen_at=presence['seen_at'] if presence else None,
          agent_working=bool(db.execute("SELECT 1 FROM accord_runs WHERE actor_id=? AND status IN ('queued','running')",(subject,)).fetchone()))
    if presence and presence['thread_id'] and pref['work_title']:
        try:
            current=access.thread_for(subject,presence['thread_id'],db)
            allowed=current['kind']=='workspace' and current['purpose']=='ordinary' and current['owner_id']==subject
            if not allowed:
                access.thread_for(viewer,current['id'],db)
                allowed=True
            if allowed:result['work']={'title':current['title'],'kind':'chat' if current['kind']=='peer' else 'work'}
        except HTTPException:pass
    for row in db.execute('''SELECT t.*,a.thread_id,a.creator_id FROM tasks t JOIN accord_task_acl a ON a.task_id=t.id
        WHERE t.assignee_id=? AND (t.assignee_id=? OR a.creator_id=?) ORDER BY t.created_at DESC''',(subject,viewer,viewer)):
        try:access.thread_for(viewer,row['thread_id'],db)
        except HTTPException:continue
        result['shared_tasks'].append({'id':row['id'],'title':row['title'],'status':row['status'],'priority':task_priority(db,row['id']),'thread_id':row['thread_id']})
    result['progress']={'completed':sum(task['status']=='done' for task in result['shared_tasks']),'total':len(result['shared_tasks']),'scope':'你有权查看的待办'}
    return result


@router.get('/members/{uid}/activity')
def member_activity(uid:str,viewer=Depends(principal)):
    with store._lock:return visible(store._conn,viewer,uid)
