from fastapi import APIRouter, Depends

from accord_api.modules.identity.session import principal
from accord_api.modules.workspace import service as service
from accord_api.modules.workspace.schemas import (
    Archive,
    Bindings,
    Move,
    NewFolder,
    RenameFolder,
    Share,
)
from accord_api.platform.commands import VersionedOperation

router = APIRouter(prefix='/api')


@router.post('/folders')
def new_folder(body: NewFolder, uid=Depends(principal)):
    return service.new_folder(body=body, uid=uid)


@router.post('/folders/{fid}/rename')
def rename_folder(fid: str, body: RenameFolder, uid=Depends(principal)):
    return service.rename_folder(fid=fid, body=body, uid=uid)


@router.post('/folders/{fid}/remove')
def remove_folder(fid: str, body: VersionedOperation, uid=Depends(principal)):
    return service.remove_folder(fid=fid, body=body, uid=uid)


@router.post('/threads/{tid}/move')
def move_thread(tid: str, body: Move, uid=Depends(principal)):
    return service.move_thread(tid=tid, body=body, uid=uid)


@router.post('/folders/{fid}/bindings')
def folder_bindings(fid: str, body: Bindings, uid=Depends(principal)):
    return service.folder_bindings(fid=fid, body=body, uid=uid)


@router.post('/threads/{tid}/bindings')
def thread_bindings(tid: str, body: Bindings, uid=Depends(principal)):
    return service.thread_bindings(tid=tid, body=body, uid=uid)


@router.get('/threads/{tid}/context')
def thread_context(tid: str, uid=Depends(principal)):
    return service.thread_context(tid=tid, uid=uid)


@router.post('/threads/{tid}/share')
def share(tid: str, body: Share, uid=Depends(principal)):
    return service.share(tid=tid, body=body, uid=uid)


@router.post('/threads/{tid}/archive')
def archive_thread(tid: str, body: Archive, uid=Depends(principal)):
    return service.archive_thread(tid=tid, body=body, uid=uid)
