from __future__ import annotations

from app.core.config import Settings
from app.core.exceptions import NotFoundError
from app.core.path_utils import normalize_document_storage_path, resolve_document_storage_path
from app.rag.loaders import load_documents_from_path
from app.rag.splitters import split_documents
from app.repositories.document_repository import DocumentRepository
from app.services.vector_store_service import VectorStoreService


class IngestionService:
    def __init__(
        self,
        settings: Settings,
        document_repository: DocumentRepository,
        vector_store_service: VectorStoreService,
    ):
        self.settings = settings
        self.document_repository = document_repository
        self.vector_store_service = vector_store_service

    def ingest_document(self, document_id: str) -> dict:
        document = self.document_repository.get(document_id)
        if not document:
            raise NotFoundError(
                code="DOCUMENT_NOT_FOUND",
                message=f"Document '{document_id}' not found.",
            )

        self.document_repository.touch(document_id, status="processing", error_message=None)

        try:
            stored_source_path = normalize_document_storage_path(document["file_path"], self.settings)
            if stored_source_path and stored_source_path != document["file_path"]:
                self.document_repository.touch(document_id, file_path=stored_source_path)
                document["file_path"] = stored_source_path
            source_path = resolve_document_storage_path(document["file_path"], self.settings)
            loaded_documents = load_documents_from_path(source_path)
            chunks = split_documents(
                loaded_documents,
                collection_id=document["collection_id"],
                document_id=document["id"],
                source_name=document["filename"],
                source_path=stored_source_path,
                chunk_size=self.settings.rag_chunk_size,
                chunk_overlap=self.settings.rag_chunk_overlap,
            )
            chunk_count = self.vector_store_service.add_documents(
                collection_id=document["collection_id"],
                chunks=chunks,
            )
            return self.document_repository.touch(
                document_id,
                status="indexed",
                chunk_count=chunk_count,
                error_message=None,
            ) or document
        except Exception as exc:
            failed = self.document_repository.touch(
                document_id,
                status="failed",
                error_message=str(exc),
            )
            if failed:
                return failed
            raise
