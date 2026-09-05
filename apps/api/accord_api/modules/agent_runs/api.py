from fastapi import APIRouter, Depends

from accord_api.modules.agent_runs import control as service
from accord_api.modules.identity.session import principal
from accord_api.platform.commands import Operation

router = APIRouter()


@router.post('/api/runs/{rid}/stop')
def stop_run(rid: str, body: Operation, uid=Depends(principal)):
    return service.stop_run(rid=rid, body=body, uid=uid)


@router.post('/api/runs/{rid}/retry')
def retry_run(rid: str, body: Operation, uid=Depends(principal)):
    return service.retry_run(rid=rid, body=body, uid=uid)
