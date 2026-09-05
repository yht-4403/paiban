from fastapi import APIRouter, Depends

from accord_api.modules.identity.session import principal
from accord_api.modules.tutorial import service

router = APIRouter(prefix='/api/tutorial')


@router.post('/prepare')
def prepare(uid=Depends(principal)):
    return service.prepare(uid)
