"""Version-preserving text replacement within the caller's transaction."""

import hashlib
import json

from accord_api.platform.db import database as store
from accord_api.platform.errors import DomainError


def replace_text(db, resource, content, title=None, kinds=('note', 'memory')):
    if resource['kind'] not in kinds or json.loads(resource['refs']):
        raise DomainError(409, '这份资料包含其他引用，请在编辑器中更新。')
    title = title or resource['title']
    if resource['body'] == content and resource['title'] == title:
        return resource['version']
    version = resource['version'] + 1
    db.execute(
        'INSERT INTO accord_resource_versions VALUES(?,?,?,?,?,?,?)',
        (
            resource['id'],
            version,
            title,
            content,
            '[]',
            hashlib.sha256((content + '[]').encode()).hexdigest(),
            store.now(),
        ),
    )
    db.execute('UPDATE accord_resources SET version=? WHERE id=?', (version, resource['id']))
    return version
