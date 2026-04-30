from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.core.config import Settings
from app.core.exceptions import ServiceUnavailableError
from app.rag.retrieval import compute_keyword_score
from app.schemas.chat import RetrievedChunk
from app.schemas.common import DocumentChunk


@dataclass
class _MilvusSymbols:
    Collection: Any
    CollectionSchema: Any
    DataType: Any
    FieldSchema: Any
    connections: Any
    utility: Any


def _load_milvus_symbols() -> _MilvusSymbols:
    try:
        from pymilvus import (  # type: ignore import-not-found
            Collection,
            CollectionSchema,
            DataType,
            FieldSchema,
            connections,
            utility,
        )
    except ImportError as exc:  # pragma: no cover - depends on optional dependency
        raise ServiceUnavailableError(
            code="MILVUS_DEPENDENCY_MISSING",
            message="pymilvus is required when VECTOR_BACKEND=milvus.",
        ) from exc

    return _MilvusSymbols(
        Collection=Collection,
        CollectionSchema=CollectionSchema,
        DataType=DataType,
        FieldSchema=FieldSchema,
        connections=connections,
        utility=utility,
    )


class MilvusVectorStoreBackend:
    def __init__(self, settings: Settings, embeddings):
        self.settings = settings
        self.embeddings = embeddings
        self._symbols: _MilvusSymbols | None = None
        self._alias = f"chatrobot-milvus-{uuid4().hex}"

    @property
    def symbols(self) -> _MilvusSymbols:
        if self._symbols is None:
            self._symbols = _load_milvus_symbols()
        return self._symbols

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _timestamp() -> int:
        return int(datetime.now(timezone.utc).timestamp())

    def _connect(self) -> None:
        try:
            self.symbols.connections.connect(
                alias=self._alias,
                **self.settings.effective_milvus_connection_args,
            )
        except Exception as exc:  # pragma: no cover - depends on runtime infra
            raise ServiceUnavailableError(
                code="MILVUS_CONNECTION_FAILED",
                message=f"Could not connect to Milvus: {exc}",
            ) from exc

    def _ensure_collection(self, embedding_dim: int):
        self._connect()
        symbols = self.symbols
        collection_name = self.settings.milvus_collection

        if symbols.utility.has_collection(collection_name, using=self._alias):
            collection = symbols.Collection(collection_name, using=self._alias)
            vector_field = next(
                (field for field in collection.schema.fields if field.name == "embedding"),
                None,
            )
            existing_dim = getattr(vector_field, "params", {}).get("dim") if vector_field else None
            if existing_dim and int(existing_dim) != int(embedding_dim):
                raise ServiceUnavailableError(
                    code="MILVUS_DIMENSION_MISMATCH",
                    message=(
                        f"Milvus collection '{collection_name}' expects dim={existing_dim}, "
                        f"but the current embedding model outputs dim={embedding_dim}."
                    ),
                )
            collection.load()
            return collection

        fields = [
            symbols.FieldSchema(
                name="id",
                dtype=symbols.DataType.VARCHAR,
                is_primary=True,
                auto_id=False,
                max_length=64,
            ),
            symbols.FieldSchema(
                name="collection_id",
                dtype=symbols.DataType.VARCHAR,
                max_length=64,
            ),
            symbols.FieldSchema(
                name="document_id",
                dtype=symbols.DataType.VARCHAR,
                max_length=64,
            ),
            symbols.FieldSchema(
                name="chunk_id",
                dtype=symbols.DataType.VARCHAR,
                max_length=128,
            ),
            symbols.FieldSchema(name="chunk_index", dtype=symbols.DataType.INT64),
            symbols.FieldSchema(
                name="text",
                dtype=symbols.DataType.VARCHAR,
                max_length=self.settings.milvus_text_max_length,
            ),
            symbols.FieldSchema(
                name="source_name",
                dtype=symbols.DataType.VARCHAR,
                max_length=self.settings.milvus_source_name_max_length,
            ),
            symbols.FieldSchema(
                name="source_path",
                dtype=symbols.DataType.VARCHAR,
                max_length=self.settings.milvus_path_max_length,
            ),
            symbols.FieldSchema(name="metadata_json", dtype=symbols.DataType.JSON),
            symbols.FieldSchema(
                name="embedding",
                dtype=symbols.DataType.FLOAT_VECTOR,
                dim=embedding_dim,
            ),
            symbols.FieldSchema(name="created_at", dtype=symbols.DataType.INT64),
        ]
        schema = symbols.CollectionSchema(
            fields=fields,
            description="ChatRobot document chunks",
            enable_dynamic_field=False,
        )
        collection = symbols.Collection(
            name=collection_name,
            schema=schema,
            using=self._alias,
            consistency_level=self.settings.milvus_consistency_level,
        )
        collection.create_index(
            field_name="embedding",
            index_params={
                "index_type": self.settings.milvus_index_type,
                "metric_type": self.settings.milvus_metric_type,
                "params": {},
            },
        )
        collection.load()
        return collection

    def _normalize_score(self, raw_score: float) -> float:
        metric = self.settings.milvus_metric_type.upper()
        if metric in {"COSINE", "IP"}:
            return float(raw_score)
        return 1.0 / (1.0 + float(raw_score))

    def add_documents(self, collection_id: str, chunks: list[DocumentChunk]) -> int:
        if not chunks:
            return 0

        texts = [chunk.chunk_text for chunk in chunks]
        vectors = self.embeddings.embed_documents(texts)
        if not vectors:
            return 0

        collection = self._ensure_collection(len(vectors[0]))
        payload = [
            [chunk.chunk_id for chunk in chunks],
            [collection_id for _ in chunks],
            [chunk.document_id for chunk in chunks],
            [chunk.chunk_id for chunk in chunks],
            [chunk.chunk_index for chunk in chunks],
            texts,
            [chunk.source_name for chunk in chunks],
            [chunk.source_path for chunk in chunks],
            [chunk.metadata for chunk in chunks],
            vectors,
            [self._timestamp() for _ in chunks],
        ]
        collection.insert(payload)
        collection.flush()
        return len(chunks)

    def similarity_search(
        self,
        collection_id: str,
        query: str,
        top_k: int,
        score_threshold: float = 0.0,
    ) -> list[RetrievedChunk]:
        self._connect()
        symbols = self.symbols
        if not symbols.utility.has_collection(self.settings.milvus_collection, using=self._alias):
            return []

        vector = self.embeddings.embed_query(query)
        collection = self._ensure_collection(len(vector))
        expr = f'collection_id == "{self._escape(collection_id)}"'
        results = collection.search(
            data=[vector],
            anns_field="embedding",
            param={
                "metric_type": self.settings.milvus_metric_type,
                "params": {},
            },
            limit=top_k,
            expr=expr,
            output_fields=[
                "collection_id",
                "document_id",
                "chunk_id",
                "chunk_index",
                "text",
                "source_name",
                "source_path",
                "metadata_json",
            ],
        )

        retrieved: list[RetrievedChunk] = []
        for hit in results[0]:
            score = self._normalize_score(hit.score)
            if score < score_threshold:
                continue
            entity = hit.entity
            metadata = entity.get("metadata_json") or {}
            retrieved.append(
                RetrievedChunk(
                    document_id=entity.get("document_id"),
                    chunk_id=entity.get("chunk_id"),
                    source_name=entity.get("source_name"),
                    source_path=entity.get("source_path"),
                    chunk_index=int(entity.get("chunk_index", 0)),
                    score=score,
                    content=entity.get("text"),
                    metadata=metadata,
                )
            )
        return retrieved

    def delete_by_document_id(self, collection_id: str, document_id: str) -> int:
        self._connect()
        symbols = self.symbols
        if not symbols.utility.has_collection(self.settings.milvus_collection, using=self._alias):
            return 0

        collection = symbols.Collection(self.settings.milvus_collection, using=self._alias)
        expr = (
            f'collection_id == "{self._escape(collection_id)}" and '
            f'document_id == "{self._escape(document_id)}"'
        )
        existing = collection.query(expr=expr, output_fields=["id"])
        if not existing:
            return 0

        collection.delete(expr=expr)
        collection.flush()
        return len(existing)

    def keyword_search(
        self,
        collection_id: str,
        query: str,
        top_k: int,
        score_threshold: float = 0.0,
    ) -> list[RetrievedChunk]:
        self._connect()
        symbols = self.symbols
        if not symbols.utility.has_collection(self.settings.milvus_collection, using=self._alias):
            return []

        collection = symbols.Collection(self.settings.milvus_collection, using=self._alias)
        expr = f'collection_id == "{self._escape(collection_id)}"'
        rows = collection.query(
            expr=expr,
            output_fields=[
                "collection_id",
                "document_id",
                "chunk_id",
                "chunk_index",
                "text",
                "source_name",
                "source_path",
                "metadata_json",
            ],
        )

        results: list[RetrievedChunk] = []
        for row in rows:
            score = compute_keyword_score(
                query,
                content=row.get("text", ""),
                source_name=row.get("source_name", ""),
            )
            if score < score_threshold:
                continue

            results.append(
                RetrievedChunk(
                    document_id=row.get("document_id", ""),
                    chunk_id=row.get("chunk_id", ""),
                    source_name=row.get("source_name", ""),
                    source_path=row.get("source_path", ""),
                    chunk_index=int(row.get("chunk_index", 0)),
                    score=score,
                    content=row.get("text", ""),
                    metadata=row.get("metadata_json") or {},
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
        self._connect()
        symbols = self.symbols
        if not symbols.utility.has_collection(self.settings.milvus_collection, using=self._alias):
            return []

        collection = symbols.Collection(self.settings.milvus_collection, using=self._alias)
        expr = (
            f'collection_id == "{self._escape(collection_id)}" and '
            f'document_id == "{self._escape(document_id)}"'
        )
        rows = collection.query(
            expr=expr,
            output_fields=[
                "collection_id",
                "document_id",
                "chunk_id",
                "chunk_index",
                "text",
                "source_name",
                "source_path",
                "metadata_json",
            ],
        )

        chunks = [
            DocumentChunk(
                document_id=row.get("document_id", document_id),
                collection_id=row.get("collection_id", collection_id),
                chunk_id=row.get("chunk_id", ""),
                chunk_index=int(row.get("chunk_index", 0)),
                chunk_text=row.get("text", ""),
                source_name=row.get("source_name", ""),
                source_path=row.get("source_path", ""),
                metadata=row.get("metadata_json") or {},
            )
            for row in rows
        ]
        chunks.sort(key=lambda item: item.chunk_index)
        if limit is not None:
            return chunks[:limit]
        return chunks
