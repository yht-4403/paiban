from typing import Literal

from pydantic import BaseModel, Field

from accord_api.platform.commands import Operation, VersionedOperation


class Preference(VersionedOperation):
    automatic: bool
    work_title: bool = False


class Heartbeat(BaseModel):
    client_id: str = Field(min_length=8, max_length=100)
    surface: Literal['work', 'chat']
    thread_id: str = Field(default='', max_length=100)
    active: bool = True


class Priority(Operation):
    priority: Literal['high', 'normal', 'low']


class Availability(Operation):
    window: Literal['open', 'closed']
