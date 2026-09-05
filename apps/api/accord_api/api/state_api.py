from fastapi import APIRouter, Depends

from accord_api.modules.identity.session import principal
from accord_api.modules.workspace import readmodel as service

router = APIRouter()


@router.get('/api/state')
def state(uid=Depends(principal)):
    return service.state(uid=uid)
