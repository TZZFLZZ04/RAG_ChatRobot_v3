from __future__ import annotations

from sqlalchemy import select

from app.db.models.collection import CollectionModel
from app.repositories.base import BaseRepository


class CollectionRepository(BaseRepository):
    def _to_dict(self, model: CollectionModel) -> dict:
        return {
            "id": model.id,
            "owner_id": model.owner_id,
            "name": model.name,
            "description": model.description,
            "vector_backend": model.vector_backend,
            "created_at": self._serialize_datetime(model.created_at),
            "updated_at": self._serialize_datetime(model.updated_at),
        }

    def list_collections(self, owner_id: str | None = None) -> list[dict]:
        with self.session_factory() as session:
            query = select(CollectionModel)
            if owner_id is not None:
                query = query.where(CollectionModel.owner_id == owner_id)
            items = session.scalars(query.order_by(CollectionModel.created_at.asc())).all()
            return [self._to_dict(item) for item in items]

    def get(self, record_id: str, owner_id: str | None = None) -> dict | None:
        with self.session_factory() as session:
            query = select(CollectionModel).where(CollectionModel.id == record_id)
            if owner_id is not None:
                query = query.where(CollectionModel.owner_id == owner_id)
            item = session.scalar(query)
            return self._to_dict(item) if item else None

    def get_by_name(self, name: str, owner_id: str | None = None) -> dict | None:
        with self.session_factory() as session:
            query = select(CollectionModel).where(CollectionModel.name == name)
            if owner_id is not None:
                query = query.where(CollectionModel.owner_id == owner_id)
            item = session.scalar(query)
            return self._to_dict(item) if item else None

    def create_collection(
        self,
        *,
        owner_id: str,
        name: str,
        description: str | None,
        vector_backend: str,
    ) -> dict:
        with self.session_factory() as session:
            item = CollectionModel(
                owner_id=owner_id,
                name=name,
                description=description,
                vector_backend=vector_backend,
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            return self._to_dict(item)
