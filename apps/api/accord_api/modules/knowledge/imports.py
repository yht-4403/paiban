"""Explicit browser-selected text imports; no access to arbitrary server file paths."""

import hashlib
from pathlib import PurePosixPath
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from accord_api.modules.knowledge.resources import create_resource
from accord_api.modules.permissions import policy as access
from accord_api.platform.commands import Operation, expect, operate
from accord_api.platform.errors import DomainError


class ImportFile(BaseModel):
    model_config = ConfigDict(extra='forbid')
    filename: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=16000)
    resource_id: Optional[str] = None
    expected_version: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode='after')
    def valid_text(self):
        try:
            self.filename.encode('utf-8')
            self.content.encode('utf-8')
        except UnicodeEncodeError:
            raise ValueError('请使用有效 UTF-8 文本。') from None
        if (
            self.filename != PurePosixPath(self.filename).name
            or '\\' in self.filename
            or self.filename.startswith('.')
        ):
            raise ValueError('请选择文件名，不要填写路径或隐藏文件。')
        if PurePosixPath(self.filename).suffix.lower() not in (
            '.md',
            '.markdown',
            '.txt',
            '.csv',
            '.json',
        ):
            raise ValueError('仅支持 Markdown、文本、CSV 和 JSON 文件。')
        if not self.content.strip() or any(ord(c) < 32 and c not in '\n\r\t' for c in self.content):
            raise ValueError('文件为空或不是可读取的文本。')
        if bool(self.resource_id) != bool(self.expected_version):
            raise ValueError('更新资料需要同时提供 ID 和版本。')
        return self


class ImportBatch(Operation):
    files: list[ImportFile] = Field(min_length=1, max_length=20)


def import_files(*, body: ImportBatch, uid):
    def run(db):
        names = [f.filename for f in body.files]
        if len(names) != len(set(names)):
            raise DomainError(422, '同一批中存在重名文件，请先重命名。')
        results = []
        for file in body.files:
            digest = hashlib.sha256(file.content.encode()).hexdigest()
            old = db.execute(
                'SELECT * FROM accord_content_imports WHERE owner_id=? AND filename=?',
                (uid, file.filename),
            ).fetchone()
            if file.resource_id:
                resource = access.resource_for(db, uid, file.resource_id)
                if not old or old['resource_id'] != file.resource_id or resource['owner_id'] != uid:
                    raise DomainError(409, '文件与原资料不匹配。')
                expect(resource['version'], file.expected_version)
                # Nested operate() would commit the batch early. Update versions in this transaction.
                from accord_api.modules.knowledge.import_writer import replace_text

                version = replace_text(db, resource, file.content)
                rid, status = resource['id'], 'updated'
            elif old:
                resource = access.resource_for(db, uid, old['resource_id'])
                if old['digest'] == digest and resource['version'] == old['resource_version']:
                    results.append(
                        dict(
                            id=resource['id'],
                            filename=file.filename,
                            version=resource['version'],
                            status='unchanged',
                        )
                    )
                    continue
                raise DomainError(
                    409, f'“{file.filename}”已导入且内容不同，请在原资料中更新，或重命名后导入。'
                )
            else:
                rid = create_resource(db, uid, PurePosixPath(file.filename).stem, file.content)
                version, status = 1, 'created'
            db.execute(
                """INSERT INTO accord_content_imports VALUES(?,?,?,?,?)
              ON CONFLICT(owner_id,filename) DO UPDATE SET resource_id=excluded.resource_id,
              digest=excluded.digest,resource_version=excluded.resource_version""",
                (uid, file.filename, rid, digest, version),
            )
            results.append(dict(id=rid, filename=file.filename, version=version, status=status))
        return {'files': results}

    return operate(uid, body, 'knowledge:import', run)
