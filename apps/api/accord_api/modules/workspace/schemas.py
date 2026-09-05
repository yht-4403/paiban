from typing import Optional

from pydantic import Field

from accord_api.platform.commands import Operation, VersionedOperation


class NewFolder(Operation):
    name: str = Field(min_length=1, max_length=60)


class RenameFolder(VersionedOperation):
    name: str = Field(min_length=1, max_length=60)


class Move(VersionedOperation):
    folder_id: str = Field(default='', max_length=100)


class Bindings(VersionedOperation):
    included: list[str] = Field(default_factory=list, max_length=20)
    excluded: list[str] = Field(default_factory=list, max_length=20)
    folder_ids: Optional[list[str]] = Field(default=None, max_length=8)


class Share(Operation):
    target_id: str
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=8000)
    source_ids: list[str] = Field(default_factory=list, max_length=12)


class Archive(Operation):
    archived: bool
