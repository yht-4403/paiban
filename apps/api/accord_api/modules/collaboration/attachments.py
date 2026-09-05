import hashlib

from accord_api.modules.knowledge.resources import create_resource
from accord_api.modules.permissions.policy import thread_for
from accord_api.platform.db import database as store
from accord_api.platform.errors import DomainError


def _safe_name(value: str) -> str:
    name = value.strip().replace('\\', '/').split('/')[-1].strip()
    if not name or name in ('.', '..'):
        raise DomainError(422, '文件名无效。')
    return name


def save(db, uid, thread, message_id, items):
    if not items:
        return []
    if (
        thread['kind'] != 'workspace'
        or thread['purpose'] != 'ordinary'
        or thread['owner_id'] != uid
        or thread['target_id'] != uid
    ):
        raise DomainError(422, '过程附件只用于自己的工作台。')
    result = []
    for item in items:
        name = _safe_name(item.filename)
        attachment_id = store.new_id('attachment')
        digest = hashlib.sha256(item.content.encode()).hexdigest()
        db.execute(
            """INSERT INTO accord_thread_attachments(
              id,thread_id,message_id,owner_id,filename,content,mime_type,size,digest,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                attachment_id,
                thread['id'],
                message_id,
                uid,
                name,
                item.content,
                item.mime_type or 'text/plain',
                len(item.content.encode()),
                digest,
                store.now(),
            ),
        )
        result.append(attachment_id)
    return result


def public_rows(db, uid, thread_ids):
    if not thread_ids:
        return []
    placeholders = ','.join('?' for _ in thread_ids)
    return [
        {
            'id': row['id'],
            'thread_id': row['thread_id'],
            'message_id': row['message_id'],
            'filename': row['filename'],
            'mime_type': row['mime_type'],
            'size': row['size'],
            'published_resource_id': row['published_resource_id'],
            'created_at': row['created_at'],
        }
        for row in db.execute(
            f"""SELECT * FROM accord_thread_attachments
                WHERE owner_id=? AND thread_id IN ({placeholders}) ORDER BY created_at,rowid""",
            (uid, *thread_ids),
        )
    ]


def publish(*, attachment_id, body, uid):
    from accord_api.platform.commands import operate

    def run(db):
        row = db.execute(
            'SELECT * FROM accord_thread_attachments WHERE id=? AND owner_id=?',
            (attachment_id, uid),
        ).fetchone()
        if not row:
            raise DomainError(404, '附件不存在。')
        thread = thread_for(uid, row['thread_id'], db)
        if thread['kind'] != 'workspace' or thread['owner_id'] != uid:
            raise DomainError(404, '附件不存在。')
        if row['published_resource_id']:
            return {'resource_id': row['published_resource_id']}
        title = row['filename'].rsplit('.', 1)[0].strip() or row['filename']
        resource_id = create_resource(db, uid, title, row['content'], scope='team')
        db.execute(
            'UPDATE accord_thread_attachments SET published_resource_id=? WHERE id=?',
            (resource_id, attachment_id),
        )
        return {'resource_id': resource_id}

    return operate(uid, body, 'publish_attachment:' + attachment_id, run)
