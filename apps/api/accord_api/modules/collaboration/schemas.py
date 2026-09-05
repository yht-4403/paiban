import base64
import binascii
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from accord_api.platform.commands import Operation


class NewThread(Operation):
    target_id: str
    title: str = Field(default='新的协作', max_length=100)
    folder_id: str = Field(default='', max_length=100)
    source_ids: list[str] = Field(default_factory=list, max_length=20)


TEXT_EXTENSIONS = frozenset(
    {'md', 'markdown', 'txt', 'csv', 'json', 'yaml', 'yml', 'log', 'ts', 'tsx', 'js', 'jsx', 'py', 'html', 'css'}
)


def readable_attachment(filename: str, mime_type: str) -> bool:
    extension = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    return mime_type.startswith('text/') or extension in TEXT_EXTENSIONS


class ProcessAttachment(BaseModel):
    filename: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=1400000)
    mime_type: str = Field(default='text/plain', max_length=100)

    @model_validator(mode='after')
    def valid_content(self):
        if readable_attachment(self.filename, self.mime_type):
            if len(self.content) > 64000:
                raise ValueError('文字附件不能超过 64000 个字符。')
            return self
        prefix = f'data:{self.mime_type};base64,'
        if not self.content.startswith(prefix):
            raise ValueError('二进制附件格式无效。')
        try:
            raw = base64.b64decode(self.content[len(prefix) :], validate=True)
        except (ValueError, binascii.Error):
            raise ValueError('二进制附件格式无效。')
        if len(raw) > 1000000:
            raise ValueError('单个附件不能超过 1 MB。')
        return self


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
        if sum(len(item.content) for item in self.attachments if readable_attachment(item.filename, item.mime_type)) > 64000:
            raise ValueError('附件总内容不能超过 64000 个字符。')
        if sum(len(item.content) for item in self.attachments) > 4200000:
            raise ValueError('附件总大小不能超过 3 MB。')
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


class TaskDelete(Operation):
    pass


class OpenChat(Operation):
    target_id: str
    new_item: bool = False
