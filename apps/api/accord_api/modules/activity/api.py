from fastapi import APIRouter, Depends

from accord_api.modules.activity import service
from accord_api.modules.activity.schemas import Availability, Heartbeat, Preference, Priority
from accord_api.modules.identity.session import principal

router = APIRouter(prefix='/api')


@router.post('/profile/activity')
def preference(body: Preference, uid=Depends(principal)):
    return service.preference(body=body, uid=uid)


@router.post('/presence')
def heartbeat(body: Heartbeat, uid=Depends(principal)):
    return service.heartbeat(body=body, uid=uid)


@router.post('/tasks/{tid}/priority')
def priority(tid: str, body: Priority, uid=Depends(principal)):
    return service.priority(tid=tid, body=body, uid=uid)


@router.get('/members/{uid}/activity')
def member_activity(uid: str, viewer=Depends(principal)):
    return service.member_activity(uid=uid, viewer=viewer)


@router.post('/profile/availability')
def availability(body: Availability, uid=Depends(principal)):
    return service.availability(body=body, uid=uid)
