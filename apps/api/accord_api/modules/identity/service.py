import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone

from accord_api.modules.identity.schemas import Credentials, Registration
from accord_api.platform.db import database as store
from accord_api.platform.errors import DomainError

COOKIE = 'accord_session'
ITERATIONS = 600_000
FIXED_PASSWORD_HASH = '00' * 16 + ':' + '00' * 32
FIXED_ACCOUNTS = (
    {
        'id': 'fixed_demo_jiancheng',
        'name': '建成',
        'agent_name': '建成的 Agent',
        'kind': 'demo',
        'role': 'owner',
    },
    {
        'id': 'fixed_demo_baotian',
        'name': '堡天',
        'agent_name': '堡天的 Agent',
        'kind': 'demo',
        'role': 'member',
    },
    {
        'id': 'fixed_demo_shuao',
        'name': '舒奥',
        'agent_name': '舒奥的 Agent',
        'kind': 'demo',
        'role': 'member',
    },
    {
        'id': 'fixed_trial_1',
        'name': '体验者一',
        'agent_name': '体验者一的 Agent',
        'kind': 'trial',
        'role': 'member',
    },
    {
        'id': 'fixed_trial_2',
        'name': '体验者二',
        'agent_name': '体验者二的 Agent',
        'kind': 'trial',
        'role': 'member',
    },
    {
        'id': 'fixed_trial_3',
        'name': '体验者三',
        'agent_name': '体验者三的 Agent',
        'kind': 'trial',
        'role': 'member',
    },
)
FIXED_ACCOUNT_BY_ID = {item['id']: item for item in FIXED_ACCOUNTS}
FIXED_ACCOUNT_IDS = tuple(FIXED_ACCOUNT_BY_ID)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    value = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return salt + ':' + value


def authenticate(token: str):
    session = store.query_one(
        """SELECT s.unit_id FROM accord_sessions s
        JOIN accord_accounts a ON a.unit_id=s.unit_id WHERE s.digest=? AND s.expires_at>?""",
        (digest(token), store.now()),
    )
    if not session:
        raise DomainError(401, '登录已失效，请重新登录。')
    return session['unit_id']


def workspace_name():
    row = store.query_one("SELECT value FROM project_state WHERE key='workspace_name'")
    return row['value'] if row else 'Accord'


def account(uid):
    row = store.query_one('SELECT unit_id,email,role FROM accord_accounts WHERE unit_id=?', (uid,))
    if not row:
        return None
    result = dict(row)
    fixed = FIXED_ACCOUNT_BY_ID.get(uid)
    if fixed:
        result.update(email='', kind=fixed['kind'])
    return result


def fixed_accounts():
    return [
        {key: item[key] for key in ('id', 'name', 'agent_name', 'kind')} for item in FIXED_ACCOUNTS
    ]


def is_fixed_account(uid):
    return uid in FIXED_ACCOUNT_BY_ID


def account_roster(uid):
    fixed = FIXED_ACCOUNT_BY_ID.get(uid)
    return fixed['kind'] if fixed else 'legacy'


def shares_account_roster(viewer, candidate):
    return account_roster(viewer) == account_roster(candidate)


def initialize_fixed_accounts():
    """Create the six selectable identities without storing a usable password."""
    created_at = store.now()
    with store.lock, store.connection():
        db = store.connection()
        for item in FIXED_ACCOUNTS:
            db.execute(
                """INSERT INTO units(id,person_name,agent_name,created_at) VALUES(?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                  person_name=excluded.person_name,agent_name=excluded.agent_name""",
                (item['id'], item['name'], item['agent_name'], created_at),
            )
            db.execute(
                """INSERT INTO accord_accounts(unit_id,email,password_hash,role,created_at)
                VALUES(?,?,?,?,?) ON CONFLICT(unit_id) DO UPDATE SET
                  email=excluded.email,password_hash=excluded.password_hash,role=excluded.role""",
                (
                    item['id'],
                    f'fixed-{item["id"]}@accord.invalid',
                    FIXED_PASSWORD_HASH,
                    item['role'],
                    created_at,
                ),
            )


def select_fixed_account(account_id):
    if account_id not in FIXED_ACCOUNT_BY_ID:
        raise DomainError(404, '可选账号不存在。')
    row = store.query_one('SELECT unit_id FROM accord_accounts WHERE unit_id=?', (account_id,))
    if not row:
        raise DomainError(503, '固定账号尚未完成初始化。')
    return row['unit_id']


def email_address(value):
    email = value.strip().casefold()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
        raise DomainError(422, '请输入有效的邮箱地址。')
    return email


def add_account(db, body, role):
    name = body.name.strip()
    if not name or len(body.password) < 12:
        raise DomainError(422, '请填写姓名，并设置至少 12 位的密码。')
    email = email_address(body.email)
    if db.execute('SELECT 1 FROM accord_accounts WHERE email=?', (email,)).fetchone():
        raise DomainError(409, '这个邮箱已注册，请直接登录。')
    uid = store.new_id('member')
    now = store.now()
    db.execute(
        'INSERT INTO units(id,person_name,agent_name,created_at) VALUES(?,?,?,?)',
        (uid, name, name + '的 Agent', now),
    )
    db.execute(
        'INSERT INTO accord_accounts VALUES(?,?,?,?,?)',
        (uid, email, password_hash(body.password), role, now),
    )
    return uid


def start_session(uid):
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    store.execute('INSERT INTO accord_sessions VALUES(?,?,?)', (digest(token), uid, expires))
    return token


def status():
    return {
        'needs_setup': False,
        'workspace': workspace_name(),
        'auth_mode': 'fixed_accounts',
    }


def setup(*, body: Registration):
    with store.lock, store.connection():
        db = store.connection()
        placeholders = ','.join('?' for _ in FIXED_ACCOUNT_IDS)
        existing = db.execute(
            f'SELECT 1 FROM accord_accounts WHERE unit_id NOT IN ({placeholders}) LIMIT 1',
            FIXED_ACCOUNT_IDS,
        ).fetchone()
        if existing:
            raise DomainError(409, '工作空间已创建，请登录或使用邀请码加入。')
        if not body.workspace.strip():
            raise DomainError(422, '请填写工作空间名称。')
        uid = add_account(db, body, 'owner')
        db.execute(
            'INSERT INTO project_state(key,value,updated_at) VALUES(?,?,?)',
            ('workspace_name', body.workspace.strip(), store.now()),
        )
    return uid


def register(*, body: Registration):
    with store.lock, store.connection():
        db = store.connection()
        invite = db.execute(
            'SELECT * FROM accord_invites WHERE digest=?', (digest(body.invite.strip()),)
        ).fetchone()
        if not invite or invite['used_by'] or invite['expires_at'] < store.now():
            raise DomainError(400, '邀请码无效、已使用或已过期，请联系工作空间创建者。')
        uid = add_account(db, body, 'member')
        db.execute('UPDATE accord_invites SET used_by=? WHERE digest=?', (uid, invite['digest']))
    return uid


def login(*, body: Credentials, ip: str):
    email = email_address(body.email)
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    scopes = [(digest('email:' + email), 10), (digest('ip:' + ip), 40)]
    with store.lock, store.connection():
        db = store.connection()
        db.execute('DELETE FROM accord_auth_attempts WHERE since<?', (cutoff,))
        for key, limit in scopes:
            row = db.execute(
                'SELECT count FROM accord_auth_attempts WHERE scope=?', (key,)
            ).fetchone()
            if row and row['count'] >= limit:
                raise DomainError(429, '登录尝试过多，请 15 分钟后再试。')
        for key, _ in scopes:
            db.execute(
                'INSERT INTO accord_auth_attempts VALUES(?,1,?) ON CONFLICT(scope) DO UPDATE SET count=count+1',
                (key, store.now()),
            )
    row = store.query_one('SELECT * FROM accord_accounts WHERE email=?', (email,))
    expected = row['password_hash'] if row else '00' * 16 + ':' + '00' * 32
    actual = password_hash(body.password, expected.split(':')[0])
    if not row or not hmac.compare_digest(expected, actual):
        raise DomainError(401, '邮箱或密码不正确。')
    store.execute('DELETE FROM accord_auth_attempts WHERE scope=?', (scopes[0][0],))
    return row['unit_id']


def logout(*, token: str):
    store.execute('DELETE FROM accord_sessions WHERE digest=?', (digest(token),))
    return {'ok': True}


def invite(*, uid):
    if account(uid)['role'] != 'owner':
        raise DomainError(403, '只有工作空间创建者可以邀请成员。')
    code = secrets.token_urlsafe(24)
    expires = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    store.execute(
        'INSERT INTO accord_invites(digest,created_by,expires_at) VALUES(?,?,?)',
        (digest(code), uid, expires),
    )
    return {'code': code, 'expires_at': expires}
