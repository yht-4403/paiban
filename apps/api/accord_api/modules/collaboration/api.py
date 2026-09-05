from fastapi import APIRouter, Depends

from accord_api.modules.collaboration import attachments, service
from accord_api.modules.collaboration.schemas import (
    AttachmentMessage,
    Confirmation,
    Handoff,
    Message,
    NewThread,
    OpenChat,
    PublishAttachment,
    TaskDelete,
    TaskStatus,
)
from accord_api.modules.identity.session import principal

router = APIRouter()


@router.post('/api/threads')
def new_thread(body: NewThread, uid=Depends(principal)):
    return service.new_thread(body=body, uid=uid)


@router.get('/api/threads/{tid}')
def thread(tid: str, person_history: bool = False, uid=Depends(principal)):
    return service.thread(tid=tid, person_history=person_history, uid=uid)


@router.post('/api/threads/{tid}/messages')
def send_message(tid: str, body: Message, uid=Depends(principal)):
    return service.send_message(tid=tid, body=body, uid=uid)


@router.post('/api/threads/{tid}/attachment-messages')
def send_attachment_message(tid: str, body: AttachmentMessage, uid=Depends(principal)):
    return service.send_message(tid=tid, body=body, uid=uid)


@router.post('/api/attachments/{attachment_id}/publish')
def publish_attachment(attachment_id: str, body: PublishAttachment, uid=Depends(principal)):
    return attachments.publish(attachment_id=attachment_id, body=body, uid=uid)


@router.get('/api/attachments/{attachment_id}')
def read_attachment(attachment_id: str, uid=Depends(principal)):
    return attachments.read(attachment_id=attachment_id, uid=uid)


@router.post('/api/threads/{tid}/handoff')
def handoff(tid: str, body: Handoff, uid=Depends(principal)):
    return service.handoff(tid=tid, body=body, uid=uid)


@router.post('/api/threads/{tid}/confirm')
def confirm(tid: str, body: Confirmation, uid=Depends(principal)):
    return service.confirm(tid=tid, body=body, uid=uid)


@router.post('/api/tasks/{task_id}/status')
def task_status(task_id: str, body: TaskStatus, uid=Depends(principal)):
    return service.task_status(task_id=task_id, body=body, uid=uid)


@router.post('/api/tasks/{task_id}/delete')
def delete_task(task_id: str, body: TaskDelete, uid=Depends(principal)):
    return service.delete_task(task_id=task_id, body=body, uid=uid)


@router.post('/api/chats/open')
def open_chat(body: OpenChat, uid=Depends(principal)):
    return service.open_chat(body=body, uid=uid)
