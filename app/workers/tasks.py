from __future__ import annotations

import logging
from time import perf_counter

from app.api.deps import get_ingestion_service, get_rag_evaluation_report_service
from app.core.metrics import observe_celery_task
from app.core.request_context import reset_context, set_context
from app.schemas.rag_eval import RagEvaluationRunRequest
from app.workers.celery_app import celery_app

task_logger = logging.getLogger("app.celery")


@celery_app.task(bind=True, name="ingest_document_task")
def ingest_document_task(self, document_id: str) -> dict:
    headers = getattr(self.request, "headers", None) or {}
    request_id = headers.get("request_id") or self.request.id
    context_tokens = set_context(
        request_id=request_id,
        correlation_id=request_id,
        task_id=self.request.id,
    )
    started_at = perf_counter()

    task_logger.info(
        "celery_task_started",
        extra={
            "extra_fields": {
                "event": "celery.task.started",
                "task_name": self.name,
                "task_state": "STARTED",
                "celery_task_id": self.request.id,
                "document_id": document_id,
            }
        },
    )

    try:
        service = get_ingestion_service()
        result = service.ingest_document(document_id)
        duration_seconds = perf_counter() - started_at
        observe_celery_task(task_name=self.name, state="SUCCESS", duration_seconds=duration_seconds)
        task_logger.info(
            "celery_task_succeeded",
            extra={
                "extra_fields": {
                    "event": "celery.task.succeeded",
                    "task_name": self.name,
                    "task_state": "SUCCESS",
                    "celery_task_id": self.request.id,
                    "document_id": document_id,
                    "document_status": result.get("status"),
                    "duration_ms": round(duration_seconds * 1000, 2),
                }
            },
        )
        return result
    except Exception:
        duration_seconds = perf_counter() - started_at
        observe_celery_task(task_name=self.name, state="FAILURE", duration_seconds=duration_seconds)
        task_logger.exception(
            "celery_task_failed",
            extra={
                "extra_fields": {
                    "event": "celery.task.failed",
                    "task_name": self.name,
                    "task_state": "FAILURE",
                    "celery_task_id": self.request.id,
                    "document_id": document_id,
                    "duration_ms": round(duration_seconds * 1000, 2),
                }
            },
        )
        raise
    finally:
        reset_context(context_tokens)


@celery_app.task(bind=True, name="run_rag_evaluation_task")
def run_rag_evaluation_task(self, payload: dict, owner_id: str) -> dict:
    headers = getattr(self.request, "headers", None) or {}
    request_id = headers.get("request_id") or self.request.id
    context_tokens = set_context(
        request_id=request_id,
        correlation_id=request_id,
        task_id=self.request.id,
    )
    started_at = perf_counter()
    total_cases = 0

    try:
        service = get_rag_evaluation_report_service()
        run_request = RagEvaluationRunRequest.model_validate(payload)
        total_cases = service.get_dataset_case_count(run_request.dataset_path)

        def update_progress(completed_cases: int, total: int) -> None:
            self.update_state(
                state="PROGRESS",
                meta={
                    "owner_id": owner_id,
                    "completed_cases": completed_cases,
                    "total_cases": total,
                },
            )

        update_progress(0, total_cases)
        stored_report = service.run_evaluation(
            run_request,
            progress_callback=update_progress,
        )
        duration_seconds = perf_counter() - started_at
        observe_celery_task(task_name=self.name, state="SUCCESS", duration_seconds=duration_seconds)
        return {
            "owner_id": owner_id,
            "completed_cases": total_cases,
            "total_cases": total_cases,
            "report_id": stored_report.report_id,
            "stored_report": stored_report.model_dump(mode="json"),
        }
    except Exception:
        duration_seconds = perf_counter() - started_at
        observe_celery_task(task_name=self.name, state="FAILURE", duration_seconds=duration_seconds)
        task_logger.exception(
            "rag_evaluation_task_failed",
            extra={
                "extra_fields": {
                    "event": "rag.evaluation.task.failed",
                    "task_name": self.name,
                    "task_state": "FAILURE",
                    "celery_task_id": self.request.id,
                    "completed_cases": 0,
                    "total_cases": total_cases,
                    "duration_ms": round(duration_seconds * 1000, 2),
                }
            },
        )
        raise
    finally:
        reset_context(context_tokens)
