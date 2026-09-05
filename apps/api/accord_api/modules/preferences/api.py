from fastapi import APIRouter, Depends

from accord_api.modules.identity.session import principal
from accord_api.modules.preferences import service as service
from accord_api.modules.preferences.schemas import ReasoningPreference

router = APIRouter(prefix='/api/profile')


@router.post('/reasoning')
def set_reasoning(body: ReasoningPreference, uid=Depends(principal)):
    return service.set_reasoning(body=body, uid=uid)
