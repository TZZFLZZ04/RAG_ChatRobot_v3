from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import Settings
from app.core.exceptions import BadRequestError, NotFoundError, ServiceUnavailableError
from app.core.path_utils import (
    build_document_storage_path,
    normalize_document_storage_path,
    resolve_document_storage_path,
)
from app.repositories.document_repository import DocumentRepository
from app.schemas.collection import CollectionIngestResponse
from app.services.collection_service import CollectionService
from app.services.ingestion_service import IngestionService
from app.services.task_queue_service import TaskQueueService
from app.services.vector_store_service import VectorStoreService


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DocumentService:
    chunk_preview_limit = 20

    def __init__(
        self,
        settings: Settings,
        collection_service: CollectionService,
        document_repository: DocumentRepository,
        ingestion_service: IngestionService,
        task_queue_service: TaskQueueService,
        vector_store_service: VectorStoreService,
    ):
        self.settings = settings
        self.collection_service = collection_service
        self.document_repository = document_repository
        self.ingestion_service = ingestion_service
        self.task_queue_service = task_queue_service
        self.vector_store_service = vector_store_service

    def _serialize_document(self, document: dict) -> dict:
        return {
            **document,
            "file_path": normalize_document_storage_path(document["file_path"], self.settings),
        }

    async def upload_document(self, upload: UploadFile, collection_id: str, owner_id: str) -> dict:
        self.collection_service.get_collection(collection_id, owner_id=owner_id)

        filename = Path(upload.filename or "").name
        if not filename:
            raise BadRequestError(code="INVALID_FILENAME", message="Upload filename is required.")

        suffix = Path(filename).suffix.lower().lstrip(".")
        if suffix not in self.settings.allowed_extensions:
            raise BadRequestError(
                code="UNSUPPORTED_FILE_TYPE",
                message=f"Allowed file types: {', '.join(sorted(self.settings.allowed_extensions))}.",
            )

        content = await upload.read()
        await upload.close()

        if len(content) > self.settings.upload_max_bytes:
            raise BadRequestError(
                code="FILE_TOO_LARGE",
                message=f"File size exceeds {self.settings.upload_max_bytes} bytes.",
            )

        document_id = str(uuid4())
        stored_name = f"{document_id}_{filename}"
        stored_relative_path = build_document_storage_path(stored_name)
        stored_path = resolve_document_storage_path(stored_relative_path, self.settings)
        stored_path.write_bytes(content)

        now = _utc_now()
        record = {
            "id": document_id,
            "owner_id": owner_id,
            "collection_id": collection_id,
            "filename": filename,
            "file_path": str(stored_relative_path),
            "file_type": suffix,
            "file_size": len(content),
            "status": "uploaded",
            "chunk_count": 0,
            "error_message": None,
            "created_at": now,
            "updated_at": now,
        }
        saved = self.document_repository.save(record)

        try:
            task_id = self.task_queue_service.enqueue_document_ingestion(document_id)
        except Exception as exc:
            self.document_repository.touch(
                document_id,
                status="uploaded",
                error_message=f"Task queue unavailable: {exc}",
            )
            raise ServiceUnavailableError(
                code="INGESTION_TASK_QUEUE_UNAVAILABLE",
                message="The document was uploaded, but the ingestion task could not be queued.",
            ) from exc

        queued = self.document_repository.touch(
            document_id,
            status="queued",
            error_message=None,
        ) or saved
        return {
            **self._serialize_document(queued),
            "task_id": task_id,
            "task_status": "queued",
        }

    def list_documents(self, owner_id: str, collection_id: str | None = None) -> list[dict]:
        documents = self.document_repository.list_documents(collection_id=collection_id, owner_id=owner_id)
        return [self._serialize_document(document) for document in documents]

    def get_document(self, document_id: str, owner_id: str) -> dict:
        document = self.document_repository.get(document_id, owner_id=owner_id)
        if not document or document.get("status") == "deleted":
            raise NotFoundError(
                code="DOCUMENT_NOT_FOUND",
                message=f"Document '{document_id}' not found.",
            )
        return document

    def get_document_detail(self, document_id: str, owner_id: str) -> dict:
        document = self.get_document(document_id, owner_id=owner_id)
        chunk_preview = []
        chunk_preview_error = None

        try:
            chunk_preview = self.vector_store_service.list_document_chunks(
                collection_id=document["collection_id"],
                document_id=document_id,
                limit=self.chunk_preview_limit,
            )
        except Exception as exc:
            chunk_preview_error = str(exc)

        return {
            **self._serialize_document(document),
            "chunk_preview": [
                {
                    "chunk_id": chunk.chunk_id,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.chunk_text,
                    "source_name": chunk.source_name,
                    "source_path": normalize_document_storage_path(chunk.source_path, self.settings),
                    "metadata": chunk.metadata,
                }
                for chunk in chunk_preview
            ],
            "chunk_preview_error": chunk_preview_error,
            "preview_limit": self.chunk_preview_limit,
        }

    def delete_document(self, document_id: str, owner_id: str) -> dict:
        document = self.get_document(document_id, owner_id=owner_id)

        self.vector_store_service.delete_by_document_id(
            collection_id=document["collection_id"],
            document_id=document_id,
        )

        file_path = resolve_document_storage_path(document["file_path"], self.settings)
        if file_path.exists():
            file_path.unlink()

        deleted = self.document_repository.touch(document_id, status="deleted")
        return self._serialize_document(deleted or document)

    def retry_document(self, document_id: str, owner_id: str) -> dict:
        document = self.get_document(document_id, owner_id=owner_id)
        if document["status"] in {"queued", "processing"}:
            raise BadRequestError(
                code="DOCUMENT_ALREADY_PROCESSING",
                message=f"Document '{document_id}' is already being processed.",
            )

        self.vector_store_service.delete_by_document_id(
            collection_id=document["collection_id"],
            document_id=document_id,
        )

        try:
            task_id = self.task_queue_service.enqueue_document_ingestion(document_id)
        except Exception as exc:
            self.document_repository.touch(
                document_id,
                error_message=f"Task queue unavailable: {exc}",
            )
            raise ServiceUnavailableError(
                code="INGESTION_TASK_QUEUE_UNAVAILABLE",
                message="The document could not be re-queued for ingestion.",
            ) from exc

        queued = self.document_repository.touch(
            document_id,
            status="queued",
            chunk_count=0,
            error_message=None,
        ) or document
        return {
            **self._serialize_document(queued),
            "task_id": task_id,
            "task_status": "queued",
        }

    def ingest_collection(self, collection_id: str, owner_id: str) -> CollectionIngestResponse:
        self.collection_service.get_collection(collection_id, owner_id=owner_id)
        documents = self.document_repository.list_documents(collection_id=collection_id, owner_id=owner_id)
        pending = [doc for doc in documents if doc["status"] in {"uploaded", "failed"}]
        task_ids: list[str] = []

        for document in pending:
            task_id = self.task_queue_service.enqueue_document_ingestion(document["id"])
            task_ids.append(task_id)
            self.document_repository.touch(
                document["id"],
                status="queued",
                error_message=None,
            )

        return CollectionIngestResponse(
            collection_id=collection_id,
            queued_count=len(pending),
            task_ids=task_ids,
        )
