from __future__ import annotations

from app.core.config import Settings
from app.core.exceptions import ServiceUnavailableError
from app.schemas.chat import RetrievedChunk
from app.schemas.common import DocumentChunk
from app.services.embedding_service import EmbeddingService
from app.vectorstores.base import VectorStoreBackend
from app.vectorstores.faiss_store import FAISSVectorStoreBackend
from app.vectorstores.milvus_store import MilvusVectorStoreBackend


class VectorStoreService:
    def __init__(self, settings: Settings, embedding_service: EmbeddingService):
        self.settings = settings
        self.embedding_service = embedding_service
        self._backend: VectorStoreBackend | None = None

    def _get_backend(self) -> VectorStoreBackend:
        if self._backend is not None:
            return self._backend

        backend_name = self.settings.vector_backend.lower()
        embeddings = self.embedding_service.get_embeddings()

        if backend_name == "faiss":
            self._backend = FAISSVectorStoreBackend(
                index_root=self.settings.faiss_index_dir,
                embeddings=embeddings,
            )
            return self._backend
        if backend_name == "milvus":
            self._backend = MilvusVectorStoreBackend(
                settings=self.settings,
                embeddings=embeddings,
            )
            return self._backend

        raise ServiceUnavailableError(
            code="VECTOR_BACKEND_NOT_IMPLEMENTED",
            message=f"Unsupported vector backend: {self.settings.vector_backend}",
        )

    def add_documents(self, collection_id: str, chunks: list[DocumentChunk]) -> int:
        return self._get_backend().add_documents(collection_id=collection_id, chunks=chunks)

    def similarity_search(
        self,
        collection_id: str,
        query: str,
        top_k: int,
        score_threshold: float = 0.0,
    ) -> list[RetrievedChunk]:
        return self._get_backend().similarity_search(
            collection_id=collection_id,
            query=query,
            top_k=top_k,
            score_threshold=score_threshold,
        )

    def delete_by_document_id(self, collection_id: str, document_id: str) -> int:
        return self._get_backend().delete_by_document_id(
            collection_id=collection_id,
            document_id=document_id,
        )

    def keyword_search(
        self,
        collection_id: str,
        query: str,
        top_k: int,
        score_threshold: float = 0.0,
    ) -> list[RetrievedChunk]:
        return self._get_backend().keyword_search(
            collection_id=collection_id,
            query=query,
            top_k=top_k,
            score_threshold=score_threshold,
        )

    def list_document_chunks(
        self,
        collection_id: str,
        document_id: str,
        limit: int | None = None,
    ) -> list[DocumentChunk]:
        return self._get_backend().list_document_chunks(
            collection_id=collection_id,
            document_id=document_id,
            limit=limit,
        )
