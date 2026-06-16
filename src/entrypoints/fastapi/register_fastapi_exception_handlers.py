"""FastAPI exception handlers."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from src.domain.exceptions import DomainValidationError, EntityNotFoundError, EntityConflictError, \
    AuthorizationError


def register_fast_api_exception_handlers(app: FastAPI):
    """Register all exception handlers for FastAPI."""

    @app.exception_handler(DomainValidationError)
    async def handle_domain_validation(
        _request: Request,
        error: DomainValidationError,
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.exception_handler(ValidationError)
    async def handle_pydantic_validation(
        _request: Request,
        error: ValidationError,
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": error.errors()})

    @app.exception_handler(EntityNotFoundError)
    async def handle_entity_not_found(
        _request: Request,
        error: EntityNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error)})

    @app.exception_handler(EntityConflictError)
    async def handle_entity_conflict(
        _request: Request,
        error: EntityConflictError,
    ) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.exception_handler(AuthorizationError)
    async def handle_authorization_error(
        _request: Request,
        error: AuthorizationError,
    ) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(error)})
