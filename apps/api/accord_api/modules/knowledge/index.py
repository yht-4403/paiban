"""Incremental, local full-text index. No model calls or permission decisions here."""

import hashlib
import json
import re


def digest(body):
    return hashlib.sha256(body.encode()).hexdigest()


def tokens(value):
    # FTS unicode61 does not split Chinese words; overlapping bigrams keep Chinese searchable.
    result = []
    for part in re.findall(r'[a-z0-9_]+|[\u4e00-\u9fff]+', value.lower()):
        if '\u4e00' <= part[0] <= '\u9fff':
            result.extend(part[i : i + 2] for i in range(max(1, len(part) - 1)))
        else:
            result.append(part)
    return list(dict.fromkeys(result))


def source_record(db, kind, sid):
    if kind == 'resource':
        row = db.execute(
            """SELECT r.owner_id,r.kind,v.* FROM accord_resources r
          JOIN accord_resource_versions v ON v.resource_id=r.id AND v.version=r.version
          WHERE r.id=? AND r.active=1 AND r.kind!='collection' """,
            (sid,),
        ).fetchone()
        if row:
            return dict(
                owner_id=row['owner_id'],
                source_kind='memory' if row['kind'] == 'memory' else 'document',
                source_id=sid,
                message_id='',
                title=row['title'],
                body=row['body'],
                version=row['version'],
                updated_at=row['created_at'],
            )
    else:
        row = db.execute(
            """SELECT m.*,t.owner_id,t.title FROM messages m
          JOIN accord_threads t ON t.id=m.conversation_id
          LEFT JOIN accord_thread_scopes s ON s.thread_id=t.id
          WHERE m.id=? AND t.kind='workspace' AND coalesce(s.purpose,'ordinary')='ordinary'
          AND m.from_kind IN ('human','agent')""",
            (sid,),
        ).fetchone()
        if row and (row['from_kind'] == 'human' or json.loads(row['meta']).get('status') == 'done'):
            return dict(
                owner_id=row['owner_id'],
                source_kind='conversation',
                source_id=row['conversation_id'],
                message_id=sid,
                title=row['title'],
                body=row['body'],
                version=1,
                updated_at=row['created_at'],
            )
    return None


def synchronize(db, limit=1000):
    pending = db.execute(
        'SELECT kind,id FROM accord_index_queue ORDER BY rowid LIMIT ?', (limit,)
    ).fetchall()
    for work in pending:
        key = work['kind'] + ':' + work['id']
        record = source_record(db, work['kind'], work['id'])
        db.execute(
            'DELETE FROM accord_content_fts WHERE chunk_id IN (SELECT id FROM accord_content_chunks WHERE source_key=?)',
            (key,),
        )
        db.execute('UPDATE accord_content_chunks SET active=0 WHERE source_key=?', (key,))
        if record:
            for offset in range(0, len(record['body']), 1300):
                body = record['body'][offset : offset + 1500]
                fingerprint = digest(body)
                cid = digest(f'{key}:{record["version"]}:{offset}:{fingerprint}')
                db.execute(
                    """INSERT INTO accord_content_chunks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1)
                  ON CONFLICT(id) DO UPDATE SET title=excluded.title,active=1""",
                    (
                        cid,
                        key,
                        record['owner_id'],
                        record['source_kind'],
                        record['source_id'],
                        record['message_id'],
                        record['title'],
                        body,
                        record['version'],
                        offset,
                        fingerprint,
                        record['updated_at'],
                    ),
                )
                terms = ' '.join(tokens(record['title'] + ' ' + body))
                db.execute('INSERT INTO accord_content_fts VALUES(?,?)', (cid, terms))
        db.execute(
            'DELETE FROM accord_index_queue WHERE kind=? AND id=?', (work['kind'], work['id'])
        )
    return db.execute('SELECT count(*) FROM accord_index_queue').fetchone()[0]
