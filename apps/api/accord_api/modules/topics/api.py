from fastapi import APIRouter, Depends

from accord_api.modules.identity.session import principal
from accord_api.modules.topics import service as service
from accord_api.modules.topics.schemas import Decision, Exploration, Handoff, NewTopic, Submission
from accord_api.platform.commands import Operation, VersionedOperation

router = APIRouter(prefix='/api/topics')


@router.post('')
def create_topic(body: NewTopic, uid=Depends(principal)):
    return service.create_topic(body=body, uid=uid)


@router.get('/{rid}')
def topic(rid: str, uid=Depends(principal)):
    return service.topic(rid=rid, uid=uid)


@router.post('/{rid}/explorations')
def explore(rid: str, body: Exploration, uid=Depends(principal)):
    return service.explore(rid=rid, body=body, uid=uid)


@router.post('/{rid}/submit')
def submit(rid: str, body: Submission, uid=Depends(principal)):
    return service.submit(rid=rid, body=body, uid=uid)


@router.post('/{rid}/withdraw')
def withdraw(rid: str, body: VersionedOperation, uid=Depends(principal)):
    return service.withdraw(rid=rid, body=body, uid=uid)


@router.post('/{rid}/release')
def release(rid: str, body: VersionedOperation, uid=Depends(principal)):
    return service.release(rid=rid, body=body, uid=uid)


@router.post('/{rid}/reviews')
def review(rid: str, body: Operation, uid=Depends(principal)):
    return service.review(rid=rid, body=body, uid=uid)


@router.post('/{rid}/decision')
def decide(rid: str, body: Decision, uid=Depends(principal)):
    return service.decide(rid=rid, body=body, uid=uid)


@router.post('/{rid}/handoff')
def handoff(rid: str, body: Handoff, uid=Depends(principal)):
    return service.handoff(rid=rid, body=body, uid=uid)
