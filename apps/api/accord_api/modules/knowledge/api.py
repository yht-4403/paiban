from typing import Optional

from fastapi import APIRouter, Depends, Query

from accord_api.modules.identity.session import principal
from accord_api.modules.knowledge import connectors, retrieval, service
from accord_api.modules.knowledge.connectors import (
    ConnectionAction,
    ConnectionScope,
    ConnectLark,
)
from accord_api.modules.knowledge.imports import ImportBatch, import_files
from accord_api.modules.knowledge.schemas import Resource, ResourceEdit, SharedDocument
from accord_api.platform.db import database as store

router = APIRouter()


@router.post('/api/documents')
def publish(body: SharedDocument, uid=Depends(principal)):
    return service.publish(body=body, uid=uid)


@router.post('/api/resources')
def create_resource(body: Resource, uid=Depends(principal)):
    return service.create_resource(body=body, uid=uid)


@router.post('/api/resources/{rid}/update')
def update_resource(rid: str, body: ResourceEdit, uid=Depends(principal)):
    return service.update_resource(rid=rid, body=body, uid=uid)


@router.get('/api/resources/{rid}')
def read_resource(
    rid: str, version: Optional[int] = Query(default=None, ge=1), uid=Depends(principal)
):
    return service.read_resource(rid=rid, version=version, uid=uid)


@router.post('/api/knowledge/imports')
def import_content(body: ImportBatch, uid=Depends(principal)):
    return import_files(body=body, uid=uid)


@router.get('/api/knowledge/search')
def search_content(q: str = Query(min_length=1, max_length=200), uid=Depends(principal)):
    with store.lock, store.connection() as db:
        return retrieval.search(db, uid, [uid], q)


@router.get('/api/knowledge/chunks/{cid}')
def read_content(cid: str, uid=Depends(principal)):
    with store.lock:
        return retrieval.read(store.connection(), cid, [uid])


@router.post('/api/knowledge/connections/lark')
def connect_lark(body: ConnectLark, uid=Depends(principal)):
    return connectors.connect(body=body, uid=uid)


@router.post('/api/knowledge/connections/{connection_id}/sync')
def sync_connection(connection_id: str, body: ConnectionAction, uid=Depends(principal)):
    return connectors.sync(connection_id=connection_id, body=body, uid=uid)


@router.post('/api/knowledge/connections/{connection_id}/disconnect')
def disconnect_connection(connection_id: str, body: ConnectionAction, uid=Depends(principal)):
    return connectors.disconnect(connection_id=connection_id, body=body, uid=uid)


@router.post('/api/knowledge/connections/{connection_id}/scope')
def share_connection(connection_id: str, body: ConnectionScope, uid=Depends(principal)):
    return connectors.set_scope(connection_id=connection_id, body=body, uid=uid)
