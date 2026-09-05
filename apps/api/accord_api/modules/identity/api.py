from fastapi import APIRouter, Depends, Request, Response

from accord_api.modules.identity import service as service
from accord_api.modules.identity.schemas import Credentials, FixedAccountSelection, Registration
from accord_api.modules.identity.session import attach, principal, request_token

router = APIRouter(prefix='/api/auth')


@router.get('/status')
def status():
    return service.status()


@router.get('/accounts')
def accounts():
    return {'workspace': service.workspace_name(), 'accounts': service.fixed_accounts()}


@router.post('/select')
def select(body: FixedAccountSelection):
    uid = service.select_fixed_account(body.account_id)
    return {'me': uid, 'session_token': service.start_session(uid)}


@router.post('/setup')
def setup(body: Registration, response: Response):
    return attach(response, service.setup(body=body))


@router.post('/register')
def register(body: Registration, response: Response):
    return attach(response, service.register(body=body))


@router.post('/login')
def login(body: Credentials, request: Request, response: Response):
    return attach(
        response, service.login(body=body, ip=request.client.host if request.client else 'local')
    )


@router.post('/logout')
def logout(request: Request, response: Response):
    result = service.logout(token=request_token(request))
    response.delete_cookie(service.COOKIE, path='/api')
    return result


@router.post('/invite')
def invite(uid=Depends(principal)):
    return service.invite(uid=uid)
