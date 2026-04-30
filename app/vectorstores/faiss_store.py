from __future__ import annotations

from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from app.rag.retrieval import compute_keyword_score
from app.schemas.chat import RetrievedChunk
from app.schemas.common import DocumentChunk


class FAISSVectorStoreBackend:
    def __init__(self, index_root: Path, embeddings):
        self.index_root = index_root
        self.embeddings = embeddings

    def _collection_path(self, collection_id: str) -> Path:
        path = self.index_root / collection_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _load_store(self, collection_id: str) -> FAISS | None:
        collection_path = self._collection_path(collection_id)
        index_file = collection_path / "index.faiss"
        if not index_file.exists():
            return None

        return FAISS.load_local(
            str(collection_path),
            self.embeddings,
            allow_dangerous_deserialization=True,
        )

    def add_documents(self, collection_id: str, chunks: list[DocumentChunk]) -> int:
        if not chunks:
            return 0

        documents = [
            Document(
                page_content=chunk.chunk_text,
                metadata={
                    "document_id": chunk.document_id,
                    "collection_id": chunk.collection_id,
                    "chunk_id": chunk.chunk_id,
                    "chunk_index": chunk.chunk_index,
                    "source_name": chunk.source_name,
                    "source_path": chunk.source_path,
                    **chunk.metadata,
                },
            )
            for chunk in chunks
        ]
        ids = [chunk.chunk_id for chunk in chunks]

        store = self._load_store(collection_id)
        if store is None:
            store = FAISS.from_documents(documents, self.embeddings, ids=ids)
        else:
            store.add_documents(documents, ids=ids)

        store.save_local(str(self._collection_path(collection_id)))
        return len(chunks)

    def similarity_search(
        self,
        collection_id: str,
        query: str,
        top_k: int,
        score_threshold: float = 0.0,
    ) -> list[RetrievedChunk]:
        store = self._load_store(collection_id)
        if store is None:
            return []

        results = store.similarity_search_with_score(query, k=top_k)
        chunks: list[RetrievedChunk] = []
        for document, distance in results:
            similarity = 1.0 / (1.0 + float(distance))
            if similarity < score_threshold:
                continue

            metadata = document.metadata or {}
            chunks.append(
                RetrievedChunk(
                    document_id=metadata.get("document_id", ""),
                    chunk_id=metadata.get("chunk_id", ""),
                    source_name=metadata.get("source_name", ""),
                    source_path=metadata.get("source_path", ""),
                    chunk_index=int(metadata.get("chunk_index", 0)),
                    score=similarity,
                    content=document.page_content,
                    metadata=metadata,
                )
            )
        return chunks

    def delete_by_document_id(self, collection_id: str, document_id: str) -> int:
        store = self._load_store(collection_id)
        if store is None:
            return 0

        docstore = getattr(store.docstore, "_dict", {})
        ids = [
            chunk_id
            for chunk_id, document in docstore.items()
            if (document.metadata or {}).get("document_id") == document_id
        ]
        if not ids:
            return 0

        store.delete(ids=ids)
        store.save_local(str(self._collection_path(collection_id)))
        return len(ids)

    def keyword_search(
        self,
        collection_id: str,
        query: str,
        top_k: int,
        score_threshold: float = 0.0,
    ) -> list[RetrievedChunk]:
        store = self._load_store(collection_id)
        if store is None:
            return []

        docstore = getattr(store.docstore, "_dict", {})
        results: list[RetrievedChunk] = []
        for document in docstore.values():
            metadata = document.metadata or {}
            if metadata.get("collection_id") != collection_id:
                continue

            score = compute_keyword_score(
                query,
                content=document.page_content,
                source_name=metadata.get("source_name", ""),
            )
            if score < score_threshold:
                continue

            results.append(
                RetrievedChunk(
                    document_id=metadata.get("document_id", ""),
                    chunk_id=metadata.get("chunk_id", ""),
                    source_name=metadata.get("source_name", ""),
                    source_path=metadata.get("source_path", ""),
                    chunk_index=int(metadata.get("chunk_index", 0)),
                    score=score,
                    content=document.page_content,
                    metadata=metadata,
                )
            )

        results.sort(
            key=lambda item: (float(item.score or 0.0), -int(item.chunk_index)),
            reverse=True,
        )
        return results[:top_k]

    def list_document_chunks(
        self,
        collection_id: str,
        document_id: str,
        limit: int | None = None,
    ) -> list[DocumentChunk]:
        store = self._load_store(collection_id)
        if store is None:
            return []

        docstore = getattr(store.docstore, "_dict", {})
        chunks: list[DocumentChunk] = []
        for document in docstore.values():
            metadata = document.metadata or {}
            if metadata.get("document_id") != document_id:
                continue
            chunks.append(
                DocumentChunk(
                    document_id=metadata.get("document_id", document_id),
                    collection_id=metadata.get("collection_id", collection_id),
                    chunk_id=metadata.get("chunk_id", ""),
                    chunk_index=int(metadata.get("chunk_index", 0)),
                    chunk_text=document.page_content,
                    source_name=metadata.get("source_name", ""),
                    source_path=metadata.get("source_path", ""),
                    metadata=metadata,
                )
            )

        chunks.sort(key=lambda item: item.chunk_index)
        if limit is not None:
            return chunks[:limit]
        return chunks
