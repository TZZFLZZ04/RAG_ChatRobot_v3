from __future__ import annotations

from uuid import uuid4

from app.core.exceptions import NotFoundError
from app.core.request_context import get_request_id
from app.schemas.rag_eval import RagEvaluationRunRequest, RagEvaluationTaskStatus


class TaskQueueService:
    def enqueue_document_ingestion(self, document_id: str) -> str:
        from app.workers.tasks import ingest_document_task

        request_id = get_request_id() or str(uuid4())
        result = ingest_document_task.apply_async(
            args=[document_id],
            headers={"request_id": request_id},
        )
        return str(result.id)

    def enqueue_rag_evaluation(self, payload: RagEvaluationRunRequest, owner_id: str) -> str:
        from app.workers.tasks import run_rag_evaluation_task

        request_id = get_request_id() or str(uuid4())
        result = run_rag_evaluation_task.apply_async(
            args=[payload.model_dump(mode="json"), owner_id],
            headers={"request_id": request_id},
        )
        return str(result.id)

    def get_rag_evaluation_status(self, task_id: str, owner_id: str) -> RagEvaluationTaskStatus:
        from app.workers.celery_app import celery_app

        task_result = celery_app.AsyncResult(task_id)
        state = str(task_result.state).upper()
        if state == "SUCCESS" and isinstance(task_result.result, dict):
            metadata = task_result.result
        elif isinstance(task_result.info, dict):
            metadata = task_result.info
        else:
            metadata = {}

        task_owner_id = metadata.get("owner_id")
        if task_owner_id and task_owner_id != owner_id:
            raise NotFoundError(
                code="RAG_EVAL_TASK_NOT_FOUND",
                message=f"RAG evaluation task '{task_id}' not found.",
            )

        if state == "SUCCESS":
            status = "completed"
        elif state == "FAILURE":
            status = "failed"
        elif state in {"PROGRESS", "STARTED", "RETRY"}:
            status = "running"
        else:
            status = "queued"

        error = str(task_result.info) if state == "FAILURE" else metadata.get("error")
        return RagEvaluationTaskStatus(
            task_id=task_id,
            status=status,
            completed_cases=int(metadata.get("completed_cases", 0)),
            total_cases=int(metadata.get("total_cases", 0)),
            report_id=metadata.get("report_id"),
            stored_report=metadata.get("stored_report"),
            error=error,
        )
