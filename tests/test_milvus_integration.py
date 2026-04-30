import os

import pytest

from app.core.config import Settings
from app.schemas.common import DocumentChunk
from app.vectorstores.milvus_store import MilvusVectorStoreBackend


pytestmark = pytest.mark.skipif(
    os.getenv("TEST_MILVUS_ENABLED") != "1",
    reason="Milvus integration test disabled. Set TEST_MILVUS_ENABLED=1 to run.",
)


class FakeEmbeddings:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]

    def embed_query(self, query: str) -> list[float]:
        return [0.1, 0.2, 0.3]


def test_milvus_backend_roundtrip() -> None:
    pytest.importorskip("pymilvus")

    settings = Settings(
        vector_backend="milvus",
        milvus_host=os.getenv("TEST_MILVUS_HOST", "localhost"),
        milvus_port=int(os.getenv("TEST_MILVUS_PORT", "19530")),
        milvus_collection=f"chatrobot_test_{os.getpid()}",
        milvus_index_type=os.getenv("TEST_MILVUS_INDEX_TYPE", "AUTOINDEX"),
        milvus_metric_type=os.getenv("TEST_MILVUS_METRIC_TYPE", "COSINE"),
    )
    backend = MilvusVectorStoreBackend(settings=settings, embeddings=FakeEmbeddings())

    chunk = DocumentChunk(
        document_id="doc-1",
        collection_id="collection-1",
        chunk_id="chunk-1",
        chunk_index=0,
        chunk_text="rose means love",
        source_name="test.txt",
        source_path="data/raw/test.txt",
        metadata={"tag": "flower"},
    )

    inserted = backend.add_documents("collection-1", [chunk])
    results = backend.similarity_search("collection-1", "rose", top_k=3)
    deleted = backend.delete_by_document_id("collection-1", "doc-1")

    assert inserted == 1
    assert results
    assert results[0].document_id == "doc-1"
    assert deleted >= 1
