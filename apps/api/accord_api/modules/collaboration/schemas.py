from typing import Literal

from pydantic import BaseModel, Field, model_validator

from accord_api.platform.commands import Operation


class NewThread(Operation):
    target_id: str
    title: str = Field(default='新的协作', max_length=100)
    folder_id: str = Field(default='', max_length=100)
    source_ids: list[str] = Field(default_factory=list, max_length=20)


class ProcessAttachment(BaseModel):
    filename: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=64000)
    mime_type: str = Field(default='text/plain', max_length=100)


class Message(Operation):
    body: str = Field(min_length=1, max_length=8000)
    source_ids: list[str] = Field(default_factory=list, max_length=10)


class AttachmentMessage(Operation):
    body: str = Field(default='', max_length=8000)
    source_ids: list[str] = Field(default_factory=list, max_length=10)
    attachments: list[ProcessAttachment] = Field(default_factory=list, max_length=5)

    @model_validator(mode='after')
    def has_content(self):
        if not self.body.strip() and not self.attachments:
            raise ValueError('消息或附件不能为空。')
        if sum(len(item.content) for item in self.attachments) > 64000:
            raise ValueError('附件总内容不能超过 64000 个字符。')
        return self


class PublishAttachment(Operation):
    pass


class Handoff(Operation):
    mode: Literal['now', 'deadline'] = 'now'
    deadline: str = ''
    note: str = Field(default='', max_length=1000)


class Confirmation(Operation):
    conclusion: str = Field(min_length=1, max_length=4000)
    task_title: str = Field(min_length=1, max_length=160)
    assignee_id: str


class TaskStatus(Operation):
    status: Literal['open', 'done']


class OpenChat(Operation):
    target_id: str
    new_item: bool = False
