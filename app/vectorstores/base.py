from __future__ import annotations

from typing import Protocol

from app.schemas.chat import RetrievedChunk
from app.schemas.common import DocumentChunk


class VectorStoreBackend(Protocol):
    def add_documents(self, collection_id: str, chunks: list[DocumentChunk]) -> int:
        ...

    def similarity_search(
        self,
        collection_id: str,
        query: str,
        top_k: int,
        score_threshold: float = 0.0,
    ) -> list[RetrievedChunk]:
        ...

    def delete_by_document_id(self, collection_id: str, document_id: str) -> int:
        ...

    def keyword_search(
        self,
        collection_id: str,
        query: str,
        top_k: int,
        score_threshold: float = 0.0,
    ) -> list[RetrievedChunk]:
        ...

    def list_document_chunks(
        self,
        collection_id: str,
        document_id: str,
        limit: int | None = None,
    ) -> list[DocumentChunk]:
        ...
