"""Accounts for one self-hosted workspace; no implicit identity switching."""
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import store

router = APIRouter(prefix='/api/auth')
COOKIE = 'accord_session'
ITERATIONS = 600_000


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    value = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return salt + ':' + value


def initialize():
    with store._lock, store._conn:
        store._conn.executescript('''
          CREATE TABLE IF NOT EXISTS accord_accounts (
            unit_id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
            role TEXT NOT NULL, created_at TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS accord_invites (
            digest TEXT PRIMARY KEY, created_by TEXT NOT NULL, expires_at TEXT NOT NULL,
            used_by TEXT NOT NULL DEFAULT '');
          CREATE TABLE IF NOT EXISTS accord_auth_attempts (
            scope TEXT PRIMARY KEY, count INTEGER NOT NULL, since TEXT NOT NULL);
        ''')


def principal(request: Request):
    token = request.cookies.get(COOKIE, '')
    session = store.query_one('''SELECT s.unit_id FROM accord_sessions s
        JOIN accord_accounts a ON a.unit_id=s.unit_id WHERE s.digest=? AND s.expires_at>?''', (digest(token), store.now()))
    if not session:
        raise HTTPException(401, '登录已失效，请重新登录。')
    return session['unit_id']


def workspace_name():
    row = store.query_one("SELECT value FROM project_state WHERE key='workspace_name'")
    return row['value'] if row else 'Accord'


def account(uid):
    row = store.query_one('SELECT unit_id,email,role FROM accord_accounts WHERE unit_id=?', (uid,))
    return dict(row) if row else None


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class Registration(Credentials):
    name: str = Field(min_length=1, max_length=40)
    workspace: str = Field(default='', max_length=80)
    invite: str = Field(default='', max_length=100)


def email_address(value):
    email = value.strip().casefold()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        raise HTTPException(422, '请输入有效的邮箱地址。')
    return email


def add_account(db, body, role):
    name = body.name.strip()
    if not name or len(body.password) < 12:
        raise HTTPException(422, '请填写姓名，并设置至少 12 位的密码。')
    email = email_address(body.email)
    if db.execute('SELECT 1 FROM accord_accounts WHERE email=?', (email,)).fetchone():
        raise HTTPException(409, '这个邮箱已注册，请直接登录。')
    uid = store.new_id('member')
    now = store.now()
    db.execute('INSERT INTO units(id,person_name,agent_name,created_at) VALUES(?,?,?,?)', (uid, name, name + '的 Agent', now))
    db.execute('INSERT INTO accord_accounts VALUES(?,?,?,?,?)', (uid, email, password_hash(body.password), role, now))
    return uid


def start_session(response, uid):
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    store.execute('INSERT INTO accord_sessions VALUES(?,?,?)', (digest(token), uid, expires))
    response.set_cookie(COOKIE, token, httponly=True, samesite='lax', secure=os.environ.get('ACCORD_COOKIE_SECURE') == '1', max_age=7*86400, path='/api')
    return {'me': uid}


@router.get('/status')
def status():
    return {'needs_setup': not bool(store.query_one('SELECT 1 FROM accord_accounts LIMIT 1')), 'workspace': workspace_name()}


@router.post('/setup')
def setup(body: Registration, response: Response):
    with store._lock, store._conn:
        db = store._conn
        if db.execute('SELECT 1 FROM accord_accounts LIMIT 1').fetchone():
            raise HTTPException(409, '工作空间已创建，请登录或使用邀请码加入。')
        if not body.workspace.strip():
            raise HTTPException(422, '请填写工作空间名称。')
        uid = add_account(db, body, 'owner')
        db.execute('INSERT INTO project_state(key,value,updated_at) VALUES(?,?,?)', ('workspace_name', body.workspace.strip(), store.now()))
    return start_session(response, uid)


@router.post('/register')
def register(body: Registration, response: Response):
    with store._lock, store._conn:
        db = store._conn
        invite = db.execute('SELECT * FROM accord_invites WHERE digest=?', (digest(body.invite.strip()),)).fetchone()
        if not invite or invite['used_by'] or invite['expires_at'] < store.now():
            raise HTTPException(400, '邀请码无效、已使用或已过期，请联系工作空间创建者。')
        uid = add_account(db, body, 'member')
        db.execute('UPDATE accord_invites SET used_by=? WHERE digest=?', (uid, invite['digest']))
    return start_session(response, uid)


@router.post('/login')
def login(body: Credentials, request: Request, response: Response):
    email = email_address(body.email)
    ip = request.client.host if request.client else 'local'
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    scopes = [(digest('email:' + email), 10), (digest('ip:' + ip), 40)]
    with store._lock, store._conn:
        db = store._conn
        db.execute('DELETE FROM accord_auth_attempts WHERE since<?', (cutoff,))
        for key, limit in scopes:
            row = db.execute('SELECT count FROM accord_auth_attempts WHERE scope=?', (key,)).fetchone()
            if row and row['count'] >= limit:
                raise HTTPException(429, '登录尝试过多，请 15 分钟后再试。')
        for key, _ in scopes:
            db.execute('INSERT INTO accord_auth_attempts VALUES(?,1,?) ON CONFLICT(scope) DO UPDATE SET count=count+1', (key, store.now()))
    row = store.query_one('SELECT * FROM accord_accounts WHERE email=?', (email,))
    expected = row['password_hash'] if row else '00'*16 + ':' + '00'*32
    actual = password_hash(body.password, expected.split(':')[0])
    if not row or not hmac.compare_digest(expected, actual):
        raise HTTPException(401, '邮箱或密码不正确。')
    store.execute('DELETE FROM accord_auth_attempts WHERE scope=?', (scopes[0][0],))
    return start_session(response, row['unit_id'])


@router.post('/logout')
def logout(request: Request, response: Response):
    store.execute('DELETE FROM accord_sessions WHERE digest=?', (digest(request.cookies.get(COOKIE, '')),))
    response.delete_cookie(COOKIE, path='/api')
    return {'ok': True}


@router.post('/invite')
def invite(uid=Depends(principal)):
    if account(uid)['role'] != 'owner':
        raise HTTPException(403, '只有工作空间创建者可以邀请成员。')
    code = secrets.token_urlsafe(24)
    expires = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    store.execute('INSERT INTO accord_invites(digest,created_by,expires_at) VALUES(?,?,?)', (digest(code), uid, expires))
    return {'code': code, 'expires_at': expires}
