from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI

from app.core.config import Settings
from app.db.session import get_engine

logger = logging.getLogger("app.observability")
_provider_initialized = False
_fastapi_instrumented = False
_sqlalchemy_instrumented = False
_celery_instrumented = False


def initialize_tracing(
    *,
    settings: Settings,
    app: FastAPI | None = None,
    celery_app: Any | None = None,
) -> None:
    if not settings.observability_tracing_enabled:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.celery import CeleryInstrumentor
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        logger.warning(
            "tracing_disabled_missing_dependencies",
            extra={
                "extra_fields": {
                    "event": "tracing.disabled",
                    "reason": "missing_dependencies",
                    "detail": str(exc),
                }
            },
        )
        return

    global _provider_initialized, _fastapi_instrumented, _sqlalchemy_instrumented, _celery_instrumented

    if not _provider_initialized:
        resource = Resource.create(
            {
                "service.name": settings.observability_service_name or settings.app_name,
                "deployment.environment": settings.app_env,
            }
        )
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=settings.observability_otlp_endpoint),
            )
        )
        trace.set_tracer_provider(provider)
        _provider_initialized = True
        logger.info(
            "tracing_initialized",
            extra={
                "extra_fields": {
                    "event": "tracing.initialized",
                    "otlp_endpoint": settings.observability_otlp_endpoint,
                }
            },
        )

    if app is not None and not _fastapi_instrumented:
        FastAPIInstrumentor.instrument_app(app)
        _fastapi_instrumented = True

    if not _sqlalchemy_instrumented:
        SQLAlchemyInstrumentor().instrument(engine=get_engine())
        _sqlalchemy_instrumented = True

    if celery_app is not None and not _celery_instrumented:
        CeleryInstrumentor().instrument()
        _celery_instrumented = True
