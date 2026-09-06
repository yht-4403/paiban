from fastapi import APIRouter, Depends

from accord_api.modules.identity.session import principal
from accord_api.modules.tutorial import service
from accord_api.platform.commands import Operation

router = APIRouter(prefix='/api/tutorial')


@router.post('/prepare')
def prepare(uid=Depends(principal)):
    return service.prepare(uid)


@router.post('/exploration/reset')
def reset_exploration(body: Operation, uid=Depends(principal)):
    return service.reset_exploration(uid, body)
