import os
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse


async def validation_error(request, error):
    return JSONResponse({'detail': '输入内容不完整或超出长度限制，请检查表单。'}, status_code=422)


async def same_origin(request: Request, call_next):
    origin = request.headers.get('origin')
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin:
        allowed = {request.headers.get('host', '')}
        configured_origin = os.environ.get('ACCORD_PUBLIC_ORIGIN', '')
        if configured_origin:
            allowed.add(urlsplit(configured_origin).netloc)
        # The local Vite development proxy preserves the originating Host header.
        if urlsplit(origin).netloc not in allowed:
            return JSONResponse(
                {'detail': '请求来源不匹配，请从工作空间页面操作。'}, status_code=403
            )
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


async def domain_error(request, error):
    return JSONResponse({'detail': error.detail}, status_code=error.status_code)
