import json

from accord_api.modules.knowledge.resources import public_resource
from accord_api.modules.permissions import policy as access
from accord_api.platform.errors import DomainError


def binding(db, uid, kind, target):
    row = db.execute(
        'SELECT * FROM accord_bindings WHERE owner_id=? AND target_kind=? AND target_id=?',
        (uid, kind, target),
    ).fetchone()
    result = (
        {
            'included': json.loads(row['included']),
            'excluded': json.loads(row['excluded']),
            'version': row['version'],
        }
        if row
        else {'included': [], 'excluded': [], 'version': 0}
    )
    result['folder_ids'] = (
        [
            r['folder_id']
            for r in db.execute(
                'SELECT folder_id FROM accord_context_folders WHERE owner_id=? AND thread_id=? ORDER BY folder_id',
                (uid, target),
            )
        ]
        if kind == 'thread'
        else []
    )
    return result


def put_binding(db, uid, kind, target, included, excluded, version, folder_ids=None):
    db.execute(
        """INSERT INTO accord_bindings VALUES(?,?,?,?,?,?)
        ON CONFLICT(owner_id,target_kind,target_id) DO UPDATE SET included=excluded.included,excluded=excluded.excluded,version=excluded.version""",
        (
            uid,
            kind,
            target,
            json.dumps(list(dict.fromkeys(included))),
            json.dumps(list(dict.fromkeys(excluded))),
            version,
        ),
    )
    if kind == 'thread' and folder_ids is not None:
        db.execute(
            'DELETE FROM accord_context_folders WHERE owner_id=? AND thread_id=?', (uid, target)
        )
        db.executemany(
            'INSERT INTO accord_context_folders VALUES(?,?,?)',
            [(uid, target, fid) for fid in dict.fromkeys(folder_ids)],
        )


def effective(db, uid, thread):
    selected = binding(db, uid, 'thread', thread['id'])
    inherited = (
        binding(db, uid, 'folder', thread['folder_id'])
        if thread['folder_id']
        else {'included': [], 'excluded': [], 'version': 0}
    )
    entries = {rid: 'folder' for rid in inherited['included'] if rid not in selected['excluded']}
    mounted = []
    for fid in selected['folder_ids']:
        folder = db.execute(
            'SELECT id,name FROM accord_folders WHERE id=? AND owner_id=?', (fid, uid)
        ).fetchone()
        if folder:
            source = binding(db, uid, 'folder', fid)
            mounted.append({**dict(folder), 'version': source['version']})
            entries.update(
                {rid: 'folder' for rid in source['included'] if rid not in selected['excluded']}
            )
    entries.update({rid: 'thread' for rid in selected['included']})
    fixed = {}
    if thread['round_id']:
        round_ = access.round_for(db, uid, thread['round_id'])
        fixed[round_['brief_id']] = 1
        if thread['purpose'] == 'review':
            if round_['stage'] == 'exploring':
                raise DomainError(409, '方案尚未公开。')
            for row in db.execute(
                'SELECT resource_id FROM accord_releases WHERE round_id=?', (round_['id'],)
            ):
                fixed[row['resource_id']] = 1
            if round_['decision_id']:
                fixed[round_['decision_id']] = 1
    entries.update({rid: 'round' for rid in fixed})
    resources = []
    for rid, origin in entries.items():
        try:
            resource = access.resource_for(db, uid, rid, fixed.get(rid))
        except DomainError:
            if origin == 'round':
                raise
            continue
        if access.compatible(db, thread, resource):
            resources.append({**public_resource(resource, False), 'origin': origin})
    return {
        'resources': resources,
        'binding': selected,
        'folder_version': inherited['version'],
        'folder_id': thread['folder_id'],
        'mounted_folders': mounted,
    }


def expand(db, uid, thread, references):
    result, seen = [], set()

    def visit(rid, version=None, depth=0):
        if depth > 4 or len(result) >= 40:
            raise DomainError(422, '资料集合过大，请减少本次使用的资料。')
        resource = access.resource_for(db, uid, rid, version)
        if not access.compatible(db, thread, resource):
            raise DomainError(403, '这份资料不能用于当前协作范围。')
        key = (rid, resource['version'])
        if key in seen:
            return
        if any(item['id'] == rid for item in result):
            raise DomainError(409, '资料集合包含同一文件的不同版本，请先统一版本。')
        seen.add(key)
        result.append({'id': rid, 'version': resource['version'], 'title': resource['title']})
        for ref in json.loads(resource['refs']):
            visit(ref['id'], ref['version'], depth + 1)

    for ref in references:
        visit(ref['id'], ref.get('version'))
    return result
