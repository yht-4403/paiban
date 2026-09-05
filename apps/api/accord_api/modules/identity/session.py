"""HTTP cookie boundary; account services receive identities, not HTTP objects."""

import os

from fastapi import Request, Response

from accord_api.modules.identity import service


def principal(request: Request):
    return service.authenticate(request_token(request))


def request_token(request: Request):
    authorization = request.headers.get('authorization', '')
    if authorization:
        scheme, separator, token = authorization.partition(' ')
        if separator and scheme.casefold() == 'bearer' and token.strip():
            return token.strip()
        return ''
    return request.cookies.get(service.COOKIE, '')


def attach(response: Response, uid: str):
    token = service.start_session(uid)
    response.set_cookie(
        service.COOKIE,
        token,
        httponly=True,
        samesite='lax',
        secure=os.environ.get('ACCORD_COOKIE_SECURE') == '1',
        max_age=7 * 86400,
        path='/api',
    )
    return {'me': uid, 'session_token': token}
