from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from accord_api.platform.commands import Operation


class Start(Operation):
    kind: Literal['sync', 'decision', 'assignment']
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=8000)
    member_ids: list[str] = Field(default_factory=list, max_length=8)
    source_ids: list[str] = Field(default_factory=list, max_length=32)


class Choose(Operation):
    member_ids: list[str] = Field(min_length=1, max_length=8)


class Sharing(Operation):
    source_kind: Literal['conversation', 'state']
    source_id: str = Field(min_length=1, max_length=100)
    enabled: bool


class Candidate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    person_id: str
    reason: str = Field(min_length=1, max_length=1000)


class Action(BaseModel):
    model_config = ConfigDict(extra='forbid')
    person_id: str
    title: str = Field(min_length=1, max_length=160)
    detail: str = Field(default='', max_length=2000)


class Outcome(BaseModel):
    model_config = ConfigDict(extra='forbid')
    summary: str = Field(min_length=1, max_length=16000)
    candidates: list[Candidate] = Field(default_factory=list, max_length=8)
    actions: list[Action] = Field(default_factory=list, max_length=12)
