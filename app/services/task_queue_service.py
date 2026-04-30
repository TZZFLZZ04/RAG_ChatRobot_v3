from __future__ import annotations

from uuid import uuid4

from app.core.request_context import get_request_id


class TaskQueueService:
    def enqueue_document_ingestion(self, document_id: str) -> str:
        from app.workers.tasks import ingest_document_task

        request_id = get_request_id() or str(uuid4())
        result = ingest_document_task.apply_async(
            args=[document_id],
            headers={"request_id": request_id},
        )
        return str(result.id)
