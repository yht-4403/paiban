"""Application composition root. Feature modules never import this module."""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from accord_api.api.middleware import domain_error, same_origin, validation_error
from accord_api.api.router import router
from accord_api.jobs.generation import lifespan
from accord_api.modules.identity.service import initialize_fixed_accounts
from accord_api.platform.db.migrations import initialize
from accord_api.platform.errors import DomainError


def create_app() -> FastAPI:
    initialize()
    initialize_fixed_accounts()
    app = FastAPI(title='Accord', docs_url=None, redoc_url=None, lifespan=lifespan)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(DomainError, domain_error)
    app.middleware('http')(same_origin)
    app.include_router(router)
    return app


app = create_app()
