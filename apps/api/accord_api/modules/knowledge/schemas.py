from typing import Literal

from pydantic import Field

from accord_api.platform.commands import Operation


class SharedDocument(Operation):
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=16000)


class Resource(Operation):
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(default='', max_length=16000)
    scope: Literal['private', 'team'] = 'private'
    resource_ids: list[str] = Field(default_factory=list, max_length=12)


class ResourceEdit(Resource):
    expected_version: int = Field(ge=1)
