from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.metrics import get_request_path, observe_http_error

audit_logger = logging.getLogger("app.audit")


class AppException(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class NotFoundError(AppException):
    def __init__(self, code: str, message: str):
        super().__init__(code=code, message=message, status_code=404)


class BadRequestError(AppException):
    def __init__(self, code: str, message: str):
        super().__init__(code=code, message=message, status_code=400)


class ServiceUnavailableError(AppException):
    def __init__(self, code: str, message: str):
        super().__init__(code=code, message=message, status_code=503)


class UnauthorizedError(AppException):
    def __init__(self, code: str, message: str):
        super().__init__(code=code, message=message, status_code=401)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        request_id = getattr(request.state, "request_id", str(uuid4()))
        observe_http_error(request=request, error_code=exc.code)
        audit_logger.warning(
            "application_error",
            extra={
                "extra_fields": {
                    "event": "http.error",
                    "error_code": exc.code,
                    "status_code": exc.status_code,
                    "method": request.method,
                    "path": get_request_path(request),
                    "client_ip": request.client.host if request.client else None,
                }
            },
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "request_id": request_id,
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", str(uuid4()))
        observe_http_error(request=request, error_code="INTERNAL_SERVER_ERROR")
        audit_logger.exception(
            "unexpected_error",
            extra={
                "extra_fields": {
                    "event": "http.error",
                    "error_code": "INTERNAL_SERVER_ERROR",
                    "status_code": 500,
                    "method": request.method,
                    "path": get_request_path(request),
                    "client_ip": request.client.host if request.client else None,
                }
            },
        )
        return JSONResponse(
            status_code=500,
            content={
                "code": "INTERNAL_SERVER_ERROR",
                "message": str(exc),
                "request_id": request_id,
            },
        )
