"""Read-only external sources that become versioned Accord resources."""

import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import ConfigDict, Field, field_validator

from accord_api.modules.knowledge.import_writer import replace_text
from accord_api.modules.knowledge.resources import create_resource
from accord_api.platform.commands import Operation, VersionedOperation, expect, operate
from accord_api.platform.config import PROJECT_ROOT
from accord_api.platform.db import database as store
from accord_api.platform.errors import DomainError

PROVIDER = 'lark_doc'
REFRESH_MINUTES = 10
MAX_CONNECTIONS = 25
MAX_CONTENT_CHARS = 200_000
TITLE_LINE = re.compile(r'^<title>(.*?)</title>\s*', re.DOTALL)


class ConnectLark(Operation):
    model_config = ConfigDict(extra='forbid')
    url: str = Field(min_length=12, max_length=1000)

    @field_validator('url')
    @classmethod
    def valid_url(cls, value):
        return normalize_lark_url(value)


class ConnectionAction(VersionedOperation):
    model_config = ConfigDict(extra='forbid')


class ConnectionScope(ConnectionAction):
    scope: Literal['private', 'team']


def normalize_lark_url(value):
    parsed = urlsplit(value.strip())
    host = (parsed.hostname or '').lower()
    allowed_host = any(
        host == suffix or host.endswith('.' + suffix) for suffix in ('feishu.cn', 'larksuite.com')
    )
    if parsed.scheme != 'https' or not allowed_host or not re.search(r'/(docx|wiki)/', parsed.path):
        raise ValueError('请粘贴飞书文档或知识库页面链接。')
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip('/'), '', ''))


def owner_only(db, uid):
    row = db.execute('SELECT role FROM accord_accounts WHERE unit_id=?', (uid,)).fetchone()
    if not row or row['role'] != 'owner':
        raise DomainError(403, '只有工作空间创建者可以连接本机飞书。')


def fetch_lark_document(locator):
    executable = shutil.which('lark-cli')
    if not executable:
        raise DomainError(503, '本机飞书连接器尚未安装。')
    env = {**os.environ, 'LARK_CLI_UPDATE_NOTIFIER': '0'}
    try:
        result = subprocess.run(
            [
                executable,
                'docs',
                '+fetch',
                '--doc',
                locator,
                '--doc-format',
                'markdown',
                '--scope',
                'full',
                '--as',
                'user',
                '--format',
                'json',
            ],
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise DomainError(503, '飞书暂时没有返回内容，请稍后同步。') from error
    if result.returncode:
        raise DomainError(503, '当前无法读取这份飞书文档，请检查本机登录和文档权限。')
    try:
        document = json.loads(result.stdout)['data']['document']
        external_id = str(document['document_id'])
        revision = str(document['revision_id'])
        raw = str(document['content'])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise DomainError(503, '飞书返回了无法识别的文档内容。') from error
    title_match = TITLE_LINE.match(raw)
    title = title_match.group(1).strip() if title_match else ''
    content = raw[title_match.end() :].strip() if title_match else raw.strip()
    if not title:
        heading = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        title = heading.group(1).strip() if heading else '飞书文档'
    if not external_id or not content:
        raise DomainError(422, '这份飞书文档没有可读取的正文。')
    if len(content) > MAX_CONTENT_CHARS:
        raise DomainError(422, '文档超过 20 万字，请拆分后连接。')
    digest = hashlib.sha256((title + '\n' + content).encode()).hexdigest()
    return {
        'external_id': external_id,
        'revision': revision,
        'title': title[:160],
        'content': content,
        'digest': digest,
    }


def public(db, row):
    resource = db.execute(
        'SELECT scope,version FROM accord_resources WHERE id=?', (row['resource_id'],)
    ).fetchone()
    return {
        **dict(row),
        'enabled': bool(row['enabled']),
        'scope': resource['scope'],
        'resource_version': resource['version'],
    }


def list_connections(db, uid):
    account = db.execute('SELECT role FROM accord_accounts WHERE unit_id=?', (uid,)).fetchone()
    if not account or account['role'] != 'owner':
        return []
    return [
        public(db, row)
        for row in db.execute(
            'SELECT * FROM accord_content_connections WHERE owner_id=? ORDER BY created_at DESC',
            (uid,),
        ).fetchall()
    ]


def connection_for(db, uid, connection_id):
    owner_only(db, uid)
    row = db.execute(
        'SELECT * FROM accord_content_connections WHERE id=? AND owner_id=?',
        (connection_id, uid),
    ).fetchone()
    if not row:
        raise DomainError(404, '连接不存在。')
    return row


def connect(*, body, uid):
    with store.lock:
        owner_only(store.connection(), uid)
    remote = fetch_lark_document(body.url)

    def run(db):
        old = db.execute(
            'SELECT * FROM accord_content_connections WHERE owner_id=? AND provider=? AND external_id=?',
            (uid, PROVIDER, remote['external_id']),
        ).fetchone()
        now = store.now()
        if old:
            resource = db.execute(
                """SELECT r.*,v.title,v.body,v.refs FROM accord_resources r
                JOIN accord_resource_versions v ON v.resource_id=r.id AND v.version=r.version
                WHERE r.id=?""",
                (old['resource_id'],),
            ).fetchone()
            replace_text(
                db,
                resource,
                remote['content'],
                title=remote['title'],
                kinds=('external',),
            )
            db.execute(
                """UPDATE accord_content_connections SET locator=?,title=?,enabled=1,status='ready',
                external_revision=?,digest=?,error_code='',checked_at=?,synced_at=?,updated_at=?,version=version+1
                WHERE id=?""",
                (
                    body.url,
                    remote['title'],
                    remote['revision'],
                    remote['digest'],
                    now,
                    now,
                    now,
                    old['id'],
                ),
            )
            return public(
                db,
                db.execute(
                    'SELECT * FROM accord_content_connections WHERE id=?', (old['id'],)
                ).fetchone(),
            )
        count = db.execute(
            'SELECT count(*) FROM accord_content_connections WHERE owner_id=? AND enabled=1',
            (uid,),
        ).fetchone()[0]
        if count >= MAX_CONNECTIONS:
            raise DomainError(409, '本机最多同时连接 25 份飞书文档。')
        resource_id = create_resource(
            db,
            uid,
            remote['title'],
            remote['content'],
            scope='private',
            kind='external',
        )
        connection_id = store.new_id('connection')
        db.execute(
            """INSERT INTO accord_content_connections
            (id,owner_id,provider,locator,external_id,title,resource_id,enabled,status,
             external_revision,digest,error_code,checked_at,synced_at,created_at,updated_at,version)
            VALUES(?,?,?,?,?,?,?,1,'ready',?,?,'',?,?,?,?,1)""",
            (
                connection_id,
                uid,
                PROVIDER,
                body.url,
                remote['external_id'],
                remote['title'],
                resource_id,
                remote['revision'],
                remote['digest'],
                now,
                now,
                now,
                now,
            ),
        )
        return public(
            db,
            db.execute(
                'SELECT * FROM accord_content_connections WHERE id=?', (connection_id,)
            ).fetchone(),
        )

    return operate(uid, body, 'content:connect:lark', run)


def sync(*, connection_id, body, uid):
    with store.lock:
        row = connection_for(store.connection(), uid, connection_id)
        expect(row['version'], body.expected_version)
        if not row['enabled']:
            raise DomainError(409, '这份飞书文档已经断开。')
        locator = row['locator']
    try:
        remote = fetch_lark_document(locator)
    except DomainError:
        with store.lock, store.connection() as db:
            current = connection_for(db, uid, connection_id)
            if current['version'] == body.expected_version:
                db.execute(
                    """UPDATE accord_content_connections SET status='error',error_code='fetch_failed',
                    checked_at=?,updated_at=?,version=version+1 WHERE id=?""",
                    (store.now(), store.now(), connection_id),
                )
        raise

    def run(db):
        current = connection_for(db, uid, connection_id)
        expect(current['version'], body.expected_version)
        if not current['enabled']:
            raise DomainError(409, '这份飞书文档已经断开。')
        if remote['external_id'] != current['external_id']:
            raise DomainError(409, '飞书链接指向的文档已经改变，请重新连接。')
        resource = db.execute(
            """SELECT r.*,v.title,v.body,v.refs FROM accord_resources r
            JOIN accord_resource_versions v ON v.resource_id=r.id AND v.version=r.version
            WHERE r.id=?""",
            (current['resource_id'],),
        ).fetchone()
        replace_text(
            db,
            resource,
            remote['content'],
            title=remote['title'],
            kinds=('external',),
        )
        now = store.now()
        db.execute(
            """UPDATE accord_content_connections SET title=?,status='ready',external_revision=?,digest=?,
            error_code='',checked_at=?,synced_at=?,updated_at=?,version=version+1 WHERE id=?""",
            (
                remote['title'],
                remote['revision'],
                remote['digest'],
                now,
                now,
                now,
                connection_id,
            ),
        )
        return public(
            db,
            db.execute(
                'SELECT * FROM accord_content_connections WHERE id=?', (connection_id,)
            ).fetchone(),
        )

    return operate(uid, body, 'content:sync:' + connection_id, run)


def disconnect(*, connection_id, body, uid):
    def run(db):
        row = connection_for(db, uid, connection_id)
        expect(row['version'], body.expected_version)
        db.execute(
            """UPDATE accord_content_connections SET enabled=0,status='disconnected',
            updated_at=?,version=version+1 WHERE id=?""",
            (store.now(), connection_id),
        )
        return public(
            db,
            db.execute(
                'SELECT * FROM accord_content_connections WHERE id=?', (connection_id,)
            ).fetchone(),
        )

    return operate(uid, body, 'content:disconnect:' + connection_id, run)


def set_scope(*, connection_id, body, uid):
    def run(db):
        row = connection_for(db, uid, connection_id)
        expect(row['version'], body.expected_version)
        db.execute(
            'UPDATE accord_resources SET scope=? WHERE id=?', (body.scope, row['resource_id'])
        )
        db.execute(
            'UPDATE accord_content_connections SET updated_at=?,version=version+1 WHERE id=?',
            (store.now(), connection_id),
        )
        return public(
            db,
            db.execute(
                'SELECT * FROM accord_content_connections WHERE id=?', (connection_id,)
            ).fetchone(),
        )

    return operate(uid, body, 'content:scope:' + connection_id, run)


def next_due():
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=REFRESH_MINUTES)).isoformat()
    return store.query_one(
        """SELECT id FROM accord_content_connections
        WHERE enabled=1 AND status IN ('ready','error') AND checked_at<?
        ORDER BY checked_at LIMIT 1""",
        (cutoff,),
    )


def sync_due(connection_id):
    with store.lock, store.connection() as db:
        row = db.execute(
            'SELECT * FROM accord_content_connections WHERE id=? AND enabled=1',
            (connection_id,),
        ).fetchone()
        if not row or row['status'] not in ('ready', 'error'):
            return
        claim_version = row['version'] + 1
        db.execute(
            "UPDATE accord_content_connections SET status='syncing',version=? WHERE id=?",
            (claim_version, connection_id),
        )
        locator = row['locator']
        external_id = row['external_id']
    try:
        remote = fetch_lark_document(locator)
    except DomainError:
        with store.lock, store.connection() as db:
            db.execute(
                """UPDATE accord_content_connections SET status='error',error_code='fetch_failed',
                checked_at=?,updated_at=?,version=version+1 WHERE id=? AND version=? AND enabled=1""",
                (store.now(), store.now(), connection_id, claim_version),
            )
        return
    with store.lock, store.connection() as db:
        current = db.execute(
            'SELECT * FROM accord_content_connections WHERE id=? AND version=? AND enabled=1',
            (connection_id, claim_version),
        ).fetchone()
        if not current:
            return
        if remote['external_id'] != external_id:
            db.execute(
                """UPDATE accord_content_connections SET status='error',error_code='source_changed',
                checked_at=?,updated_at=?,version=version+1 WHERE id=?""",
                (store.now(), store.now(), connection_id),
            )
            return
        resource = db.execute(
            """SELECT r.*,v.title,v.body,v.refs FROM accord_resources r
            JOIN accord_resource_versions v ON v.resource_id=r.id AND v.version=r.version
            WHERE r.id=?""",
            (current['resource_id'],),
        ).fetchone()
        replace_text(
            db,
            resource,
            remote['content'],
            title=remote['title'],
            kinds=('external',),
        )
        now = store.now()
        db.execute(
            """UPDATE accord_content_connections SET title=?,status='ready',external_revision=?,digest=?,
            error_code='',checked_at=?,synced_at=?,updated_at=?,version=version+1 WHERE id=?""",
            (
                remote['title'],
                remote['revision'],
                remote['digest'],
                now,
                now,
                now,
                connection_id,
            ),
        )
