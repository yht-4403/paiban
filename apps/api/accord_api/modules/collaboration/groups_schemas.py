from pydantic import Field, model_validator

from accord_api.modules.collaboration.schemas import (
    MAX_TOTAL_ATTACHMENT_CONTENT_LENGTH,
    ProcessAttachment,
    readable_attachment,
)
from accord_api.platform.commands import Operation


class CreateGroup(Operation):
    member_ids: list[str] = Field(min_length=2, max_length=7)
    title: str = Field(default='', max_length=80)


class AddMembers(Operation):
    member_ids: list[str] = Field(min_length=1, max_length=7)


class RenameGroup(Operation):
    title: str = Field(min_length=1, max_length=80)


class GroupMessage(Operation):
    body: str = Field(default='', max_length=8000)
    agent_id: str = Field(default='', max_length=100)
    source_ids: list[str] = Field(default_factory=list, max_length=10)
    attachments: list[ProcessAttachment] = Field(default_factory=list, max_length=5)

    @model_validator(mode='after')
    def has_content(self):
        if not self.body.strip() and not self.attachments:
            raise ValueError('消息或附件不能为空。')
        if sum(len(item.content) for item in self.attachments if readable_attachment(item.filename, item.mime_type)) > 64000:
            raise ValueError('附件总内容不能超过 64000 个字符。')
        if sum(len(item.content) for item in self.attachments) > MAX_TOTAL_ATTACHMENT_CONTENT_LENGTH:
            raise ValueError('附件总大小不能超过 20 MB。')
        return self
