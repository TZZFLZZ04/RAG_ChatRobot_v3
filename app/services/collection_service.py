from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.exceptions import BadRequestError, NotFoundError
from app.db.session import get_session_factory
from app.repositories.collection_repository import CollectionRepository
from app.schemas.collection import CollectionCreateRequest


class CollectionService:
    def __init__(
        self,
        settings: Settings,
        collection_repository: CollectionRepository | None = None,
    ):
        self.settings = settings
        self.collection_repository = collection_repository or CollectionRepository(
            get_session_factory()
        )

    def create_collection(self, payload: CollectionCreateRequest, owner_id: str) -> dict:
        existing = self.collection_repository.get_by_name(payload.name, owner_id=owner_id)
        if existing:
            raise BadRequestError(
                code="COLLECTION_ALREADY_EXISTS",
                message=f"Collection '{payload.name}' already exists.",
            )

        try:
            return self.collection_repository.create_collection(
                owner_id=owner_id,
                name=payload.name,
                description=payload.description,
                vector_backend=self.settings.vector_backend,
            )
        except IntegrityError as exc:
            raise BadRequestError(
                code="COLLECTION_ALREADY_EXISTS",
                message=f"Collection '{payload.name}' already exists.",
            ) from exc

    def list_collections(self, owner_id: str) -> list[dict]:
        return self.collection_repository.list_collections(owner_id=owner_id)

    def get_collection(self, collection_id: str, owner_id: str) -> dict:
        collection = self.collection_repository.get(collection_id, owner_id=owner_id)
        if not collection:
            raise NotFoundError(
                code="COLLECTION_NOT_FOUND",
                message=f"Collection '{collection_id}' not found.",
            )
        return collection
