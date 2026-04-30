from __future__ import annotations

from celery import Celery

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.tracing import initialize_tracing


def create_celery_app() -> Celery:
    settings = get_settings()
    configure_logging(settings.app_debug, settings.observability_log_json)
    app = Celery("chatrobot")
    app.conf.update(
        broker_url=settings.effective_celery_broker_url,
        result_backend=settings.effective_celery_result_backend,
        task_always_eager=settings.celery_task_always_eager,
        task_ignore_result=settings.celery_task_ignore_result,
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="Asia/Shanghai",
        enable_utc=True,
        task_default_queue=settings.celery_ingestion_queue,
        worker_hijack_root_logger=False,
    )
    app.autodiscover_tasks(["app.workers"])
    initialize_tracing(settings=settings, celery_app=app)
    return app


celery_app = create_celery_app()
