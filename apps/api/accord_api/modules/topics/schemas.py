from pydantic import Field

from accord_api.platform.commands import Operation, VersionedOperation


class NewTopic(Operation):
    title: str = Field(min_length=1, max_length=100)
    brief: str = Field(min_length=1, max_length=8000)
    member_ids: list[str] = Field(min_length=1, max_length=30)
    source_ids: list[str] = Field(default_factory=list, max_length=10)
    deadline: str = Field(default='', max_length=50)


class Exploration(Operation):
    title: str = Field(default='新的方向', min_length=1, max_length=100)
    folder_id: str = Field(default='', max_length=100)


class Submission(VersionedOperation):
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=12000)
    source_ids: list[str] = Field(default_factory=list, max_length=10)


class Direction(VersionedOperation):
    label: str = Field(min_length=1, max_length=100)


class Decision(VersionedOperation):
    body: str = Field(min_length=1, max_length=4000)
    proposal_ids: list[str] = Field(min_length=1, max_length=30)


class Handoff(Operation):
    target_id: str
    task_title: str = Field(min_length=1, max_length=160)
