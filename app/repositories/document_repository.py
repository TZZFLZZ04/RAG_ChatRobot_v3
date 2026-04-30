from __future__ import annotations

from sqlalchemy import select

from app.db.models.document import DocumentModel, utc_now
from app.repositories.base import BaseRepository


class DocumentRepository(BaseRepository):
    def _to_dict(self, model: DocumentModel) -> dict:
        return {
            "id": model.id,
            "owner_id": model.owner_id,
            "collection_id": model.collection_id,
            "filename": model.filename,
            "file_path": model.file_path,
            "file_type": model.file_type,
            "file_size": model.file_size,
            "status": model.status,
            "chunk_count": model.chunk_count,
            "error_message": model.error_message,
            "created_at": self._serialize_datetime(model.created_at),
            "updated_at": self._serialize_datetime(model.updated_at),
        }

    def save(self, record: dict) -> dict:
        with self.session_factory() as session:
            item = DocumentModel(**record)
            session.add(item)
            session.commit()
            session.refresh(item)
            return self._to_dict(item)

    def get(self, record_id: str, owner_id: str | None = None) -> dict | None:
        with self.session_factory() as session:
            query = select(DocumentModel).where(DocumentModel.id == record_id)
            if owner_id is not None:
                query = query.where(DocumentModel.owner_id == owner_id)
            item = session.scalar(query)
            return self._to_dict(item) if item else None

    def list_documents(self, collection_id: str | None = None, owner_id: str | None = None) -> list[dict]:
        with self.session_factory() as session:
            query = select(DocumentModel).where(DocumentModel.status != "deleted")
            if collection_id is not None:
                query = query.where(DocumentModel.collection_id == collection_id)
            if owner_id is not None:
                query = query.where(DocumentModel.owner_id == owner_id)
            items = session.scalars(query.order_by(DocumentModel.created_at.desc())).all()
            return [self._to_dict(item) for item in items]

    def touch(self, document_id: str, **updates) -> dict | None:
        with self.session_factory() as session:
            item = session.get(DocumentModel, document_id)
            if not item:
                return None
            for key, value in updates.items():
                setattr(item, key, value)
            item.updated_at = utc_now()
            session.commit()
            session.refresh(item)
            return self._to_dict(item)
