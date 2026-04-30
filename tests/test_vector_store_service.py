import pytest

from app.core.config import Settings
from app.core.exceptions import ServiceUnavailableError
from app.services.vector_store_service import VectorStoreService
from app.vectorstores.faiss_store import FAISSVectorStoreBackend
from app.vectorstores.milvus_store import MilvusVectorStoreBackend


class DummyEmbeddingService:
    def get_embeddings(self):
        return object()


def test_selects_faiss_backend() -> None:
    settings = Settings(vector_backend="faiss")
    service = VectorStoreService(settings=settings, embedding_service=DummyEmbeddingService())

    backend = service._get_backend()

    assert isinstance(backend, FAISSVectorStoreBackend)


def test_selects_milvus_backend() -> None:
    settings = Settings(vector_backend="milvus")
    service = VectorStoreService(settings=settings, embedding_service=DummyEmbeddingService())

    backend = service._get_backend()

    assert isinstance(backend, MilvusVectorStoreBackend)


def test_unknown_backend_raises() -> None:
    settings = Settings(vector_backend="unknown")
    service = VectorStoreService(settings=settings, embedding_service=DummyEmbeddingService())

    with pytest.raises(ServiceUnavailableError):
        service._get_backend()


def test_milvus_connection_args_use_uri_and_token() -> None:
    settings = Settings(
        vector_backend="milvus",
        milvus_uri="http://milvus:19530",
        milvus_token="secret-token",
    )

    assert settings.effective_milvus_connection_args == {
        "uri": "http://milvus:19530",
        "token": "secret-token",
    }
