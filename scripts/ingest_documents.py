from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings
from app.db.session import init_db, get_session_factory
from app.repositories.document_repository import DocumentRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import UserRegisterRequest
from app.schemas.collection import CollectionCreateRequest
from app.services.collection_service import CollectionService
from app.services.embedding_service import EmbeddingService
from app.services.ingestion_service import IngestionService
from app.services.user_service import UserService
from app.services.vector_store_service import VectorStoreService


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ingest_directory(directory: str, collection_name: str | None = None) -> None:
    settings = get_settings()
    init_db()
    user_service = UserService(UserRepository(get_session_factory()))
    owner = user_service.user_repository.get_by_username("local_admin")
    if not owner:
        owner = user_service.register(
            UserRegisterRequest(
                username="local_admin",
                email="local_admin@example.com",
                password="ChangeMe123",
            )
        )
    collection_service = CollectionService(settings=settings)
    if not collection_name:
        existing = collection_service.collection_repository.get_by_name(settings.default_collection_name)
        collection = existing or collection_service.create_collection(
            CollectionCreateRequest(
                name=settings.default_collection_name,
                description="CLI import default collection",
            ),
            owner_id=owner["id"],
        )
    else:
        existing = collection_service.collection_repository.get_by_name(collection_name)
        collection = existing or collection_service.create_collection(
            CollectionCreateRequest(name=collection_name, description="CLI import"),
            owner_id=owner["id"],
        )

    document_repository = DocumentRepository(get_session_factory())
    ingestion_service = IngestionService(
        settings=settings,
        document_repository=document_repository,
        vector_store_service=VectorStoreService(
            settings=settings,
            embedding_service=EmbeddingService(settings),
        ),
    )

    for file_path in Path(directory).iterdir():
        if not file_path.is_file():
            continue
        suffix = file_path.suffix.lower().lstrip(".")
        if suffix not in settings.allowed_extensions:
            continue

        now = utc_now()
        record = {
            "id": str(uuid4()),
            "owner_id": owner["id"],
            "collection_id": collection["id"],
            "filename": file_path.name,
            "file_path": str(file_path.resolve()),
            "file_type": suffix,
            "file_size": file_path.stat().st_size,
            "status": "uploaded",
            "chunk_count": 0,
            "error_message": None,
            "created_at": now,
            "updated_at": now,
        }
        document_repository.save(record)
        ingestion_service.ingest_document(record["id"])
        print(f"Ingested: {file_path.name}")


if __name__ == "__main__":
    ingest_directory("OneFlower")
