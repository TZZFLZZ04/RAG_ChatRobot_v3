from __future__ import annotations

from app.api import deps
from app.core.config import get_settings
from app.db.session import get_engine, get_session_factory


def reset_dependency_caches() -> None:
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    deps.get_collection_repository.cache_clear()
    deps.get_document_repository.cache_clear()
    deps.get_conversation_repository.cache_clear()
    deps.get_user_repository.cache_clear()
    deps.get_embedding_service.cache_clear()
    deps.get_vector_store_service.cache_clear()
    deps.get_retrieval_service.cache_clear()
    deps.get_ingestion_service.cache_clear()
    deps.get_collection_service.cache_clear()
    deps.get_conversation_service.cache_clear()
    deps.get_document_service.cache_clear()
    deps.get_chat_service.cache_clear()
    deps.get_user_service.cache_clear()
