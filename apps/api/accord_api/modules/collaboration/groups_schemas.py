from pydantic import Field

from accord_api.platform.commands import Operation


class CreateGroup(Operation):
    member_ids: list[str] = Field(min_length=2, max_length=7)
    title: str = Field(default='', max_length=80)


class AddMembers(Operation):
    member_ids: list[str] = Field(min_length=1, max_length=7)


class RenameGroup(Operation):
    title: str = Field(min_length=1, max_length=80)


class GroupMessage(Operation):
    body: str = Field(min_length=1, max_length=8000)
    agent_id: str = Field(default='', max_length=100)
    source_ids: list[str] = Field(default_factory=list, max_length=10)
