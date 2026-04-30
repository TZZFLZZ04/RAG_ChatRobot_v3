from functools import lru_cache

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from app.core.config import Settings, get_settings
from app.core.exceptions import UnauthorizedError
from app.core.security import decode_access_token
from app.db.session import get_session_factory
from app.repositories.collection_repository import CollectionRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.user_repository import UserRepository
from app.services.chat_service import ChatService
from app.services.collection_service import CollectionService
from app.services.conversation_service import ConversationService
from app.services.document_service import DocumentService
from app.services.embedding_service import EmbeddingService
from app.services.ingestion_service import IngestionService
from app.services.retrieval_service import RetrievalService
from app.services.task_queue_service import TaskQueueService
from app.services.user_service import UserService
from app.services.vector_store_service import VectorStoreService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


@lru_cache
def get_user_repository() -> UserRepository:
    return UserRepository(get_session_factory())


@lru_cache
def get_collection_repository() -> CollectionRepository:
    return CollectionRepository(get_session_factory())


@lru_cache
def get_document_repository() -> DocumentRepository:
    return DocumentRepository(get_session_factory())


@lru_cache
def get_conversation_repository() -> ConversationRepository:
    return ConversationRepository(get_session_factory())


@lru_cache
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService(get_settings())


@lru_cache
def get_vector_store_service() -> VectorStoreService:
    return VectorStoreService(
        settings=get_settings(),
        embedding_service=get_embedding_service(),
    )


@lru_cache
def get_retrieval_service() -> RetrievalService:
    return RetrievalService(get_vector_store_service(), get_settings())


@lru_cache
def get_ingestion_service() -> IngestionService:
    return IngestionService(
        settings=get_settings(),
        document_repository=get_document_repository(),
        vector_store_service=get_vector_store_service(),
    )


@lru_cache
def get_collection_service() -> CollectionService:
    return CollectionService(
        settings=get_settings(),
        collection_repository=get_collection_repository(),
    )


@lru_cache
def get_user_service() -> UserService:
    return UserService(get_user_repository())


@lru_cache
def get_task_queue_service() -> TaskQueueService:
    return TaskQueueService()


@lru_cache
def get_document_service() -> DocumentService:
    return DocumentService(
        settings=get_settings(),
        collection_service=get_collection_service(),
        document_repository=get_document_repository(),
        ingestion_service=get_ingestion_service(),
        task_queue_service=get_task_queue_service(),
        vector_store_service=get_vector_store_service(),
    )


@lru_cache
def get_chat_service() -> ChatService:
    return ChatService(
        settings=get_settings(),
        collection_service=get_collection_service(),
        conversation_repository=get_conversation_repository(),
        retrieval_service=get_retrieval_service(),
    )


@lru_cache
def get_conversation_service() -> ConversationService:
    return ConversationService(
        conversation_repository=get_conversation_repository(),
    )


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    settings = get_settings()
    try:
        payload = decode_access_token(token, settings=settings)
    except Exception as exc:
        raise UnauthorizedError(code="INVALID_TOKEN", message="登录状态无效，请重新登录。") from exc
    user = get_user_service().get_user(payload["sub"])
    if not user:
        raise UnauthorizedError(code="USER_NOT_FOUND", message="用户不存在。")
    return user
