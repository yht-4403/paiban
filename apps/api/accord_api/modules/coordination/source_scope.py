"""Validate the explicit resource boundary of a coordination flow."""

from accord_api.modules.permissions import policy as access
from accord_api.platform.errors import DomainError


def validate(db, members, source_ids):
    """Return de-duplicated IDs after checking visibility and owner coverage."""
    selected = list(dict.fromkeys(source_ids))
    if not selected:
        return []

    resources = []
    for resource_id in selected:
        row = db.execute(
            'SELECT * FROM accord_resources WHERE id=? AND active=1', (resource_id,)
        ).fetchone()
        if (
            not row
            or row['kind'] == 'collection'
            or row['owner_id'] not in members
            or not all(access.can_read(db, member, row) for member in members)
        ):
            # Keep missing, private, and cross-roster IDs indistinguishable at the API boundary.
            raise DomainError(422, '请选择本轮每位成员都可读取的资料。')
        resources.append(row)

    owners = {row['owner_id'] for row in resources}
    if owners != set(members):
        raise DomainError(422, '请为本轮每位成员至少选择一份本人资料。')
    return selected
