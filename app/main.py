from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.metrics import observe_http_request, render_metrics_response
from app.core.request_context import reset_context, set_context
from app.core.tracing import initialize_tracing
from app.db.session import init_db
from app.web.router import FRONTEND_DIR, router as web_router

http_logger = logging.getLogger("app.http")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.ensure_directories()
    configure_logging(settings.app_debug, settings.observability_log_json)
    initialize_tracing(settings=settings, app=app)
    if settings.db_auto_init:
        init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        debug=settings.app_debug,
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        request.state.request_id = request_id
        context_tokens = set_context(request_id=request_id, correlation_id=request_id)
        started_at = perf_counter()
        response = None

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            duration_seconds = perf_counter() - started_at
            status_code = getattr(response, "status_code", 500)
            http_logger.info(
                "request_completed",
                extra={
                    "extra_fields": {
                        "event": "http.request.completed",
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": status_code,
                        "duration_ms": round(duration_seconds * 1000, 2),
                        "client_ip": request.client.host if request.client else None,
                    }
                },
            )
            if settings.observability_metrics_enabled:
                observe_http_request(
                    request=request,
                    status_code=status_code,
                    duration_seconds=duration_seconds,
                )
            reset_context(context_tokens)

    if settings.observability_metrics_enabled:
        @app.get("/metrics", include_in_schema=False)
        def metrics():
            return render_metrics_response()

    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static")), name="static")
    app.include_router(web_router)
    app.include_router(api_router, prefix=settings.api_prefix)
    register_exception_handlers(app)
    return app


app = create_app()
