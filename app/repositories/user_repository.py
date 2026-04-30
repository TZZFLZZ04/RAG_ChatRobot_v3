from __future__ import annotations

from sqlalchemy import or_, select

from app.db.models.user import UserModel
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    def _to_dict(self, model: UserModel) -> dict:
        return {
            "id": model.id,
            "username": model.username,
            "email": model.email,
            "hashed_password": model.hashed_password,
            "is_active": model.is_active,
            "created_at": self._serialize_datetime(model.created_at),
            "updated_at": self._serialize_datetime(model.updated_at),
        }

    def create_user(self, *, username: str, email: str, hashed_password: str) -> dict:
        with self.session_factory() as session:
            item = UserModel(
                username=username,
                email=email,
                hashed_password=hashed_password,
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            return self._to_dict(item)

    def get(self, user_id: str) -> dict | None:
        with self.session_factory() as session:
            item = session.get(UserModel, user_id)
            return self._to_dict(item) if item else None

    def get_by_username(self, username: str) -> dict | None:
        with self.session_factory() as session:
            item = session.scalar(select(UserModel).where(UserModel.username == username))
            return self._to_dict(item) if item else None

    def get_by_email(self, email: str) -> dict | None:
        with self.session_factory() as session:
            item = session.scalar(select(UserModel).where(UserModel.email == email))
            return self._to_dict(item) if item else None

    def get_by_username_or_email(self, identifier: str) -> dict | None:
        with self.session_factory() as session:
            item = session.scalar(
                select(UserModel).where(
                    or_(UserModel.username == identifier, UserModel.email == identifier)
                )
            )
            return self._to_dict(item) if item else None
