from fastapi import APIRouter, Depends

from accord_api.modules.collaboration import groups as service
from accord_api.modules.collaboration.groups_schemas import (
    AddMembers,
    CreateGroup,
    GroupMessage,
    RenameGroup,
)
from accord_api.modules.identity.session import principal

router = APIRouter(prefix='/api/groups')


@router.post('')
def create_group(body: CreateGroup, uid=Depends(principal)):
    return service.create_group(body=body, uid=uid)


@router.post('/{tid}/members')
def add_members(tid: str, body: AddMembers, uid=Depends(principal)):
    return service.add_members(tid=tid, body=body, uid=uid)


@router.post('/{tid}/rename')
def rename_group(tid: str, body: RenameGroup, uid=Depends(principal)):
    return service.rename_group(tid=tid, body=body, uid=uid)


@router.post('/{tid}/messages')
def send_message(tid: str, body: GroupMessage, uid=Depends(principal)):
    return service.send_message(tid=tid, body=body, uid=uid)
