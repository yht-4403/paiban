from fastapi import APIRouter, Depends

from accord_api.modules.coordination import service, task_completion
from accord_api.modules.coordination.schemas import Choose, Sharing, Start
from accord_api.modules.identity.session import principal
from accord_api.platform.commands import Operation

router = APIRouter()


@router.post('/api/flows')
def start(body: Start, uid=Depends(principal)):
    return service.start(body, uid)


@router.get('/api/flows/{fid}')
def detail(fid: str, uid=Depends(principal)):
    return service.detail(uid, fid)


@router.post('/api/flows/{fid}/choose')
def choose(fid: str, body: Choose, uid=Depends(principal)):
    return service.choose(body, uid, fid)


@router.post('/api/flows/{fid}/finish')
def finish(fid: str, body: Operation, uid=Depends(principal)):
    return service.finish_meeting(body, uid, fid)


@router.post('/api/flows/{fid}/retry')
def retry(fid: str, body: Operation, uid=Depends(principal)):
    return service.retry(body, uid, fid)


@router.post('/api/flow-actions/{aid}/accept')
def accept(aid: str, body: Operation, uid=Depends(principal)):
    return service.action(body, uid, aid, True)


@router.post('/api/flow-actions/{aid}/dismiss')
def dismiss(aid: str, body: Operation, uid=Depends(principal)):
    return service.action(body, uid, aid, False)


@router.post('/api/threads/{tid}/close')
def close(tid: str, body: Operation, uid=Depends(principal)):
    return service.close_chat(body, uid, tid)


@router.get('/api/context-sharing')
def sharing(uid=Depends(principal)):
    return service.sharing(uid)


@router.post('/api/context-sharing')
def share(body: Sharing, uid=Depends(principal)):
    return service.set_sharing(body, uid)


@router.post('/api/tasks/{task_id}/tick')
def tick_task(task_id: str, body: task_completion.Tick, uid=Depends(principal)):
    return task_completion.tick(body, uid, task_id)


@router.post('/api/task-summaries/{fid}/reply')
def task_reply(fid: str, body: task_completion.Reply, uid=Depends(principal)):
    return task_completion.update(body, uid, fid, 'reply')


@router.post('/api/task-summaries/{fid}/retry')
def task_retry(fid: str, body: Operation, uid=Depends(principal)):
    return task_completion.update(body, uid, fid, 'retry')


@router.post('/api/task-summaries/{fid}/cancel')
def task_cancel(fid: str, body: Operation, uid=Depends(principal)):
    return task_completion.update(body, uid, fid, 'cancel')
