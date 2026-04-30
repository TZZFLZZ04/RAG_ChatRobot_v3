from __future__ import annotations

from sqlalchemy import desc
from sqlalchemy import select

from app.db.models.conversation import ConversationModel, utc_now as conversation_utc_now
from app.db.models.message import MessageModel
from app.repositories.base import BaseRepository


class ConversationRepository(BaseRepository):
    def _conversation_to_dict(self, model: ConversationModel) -> dict:
        return {
            "id": model.id,
            "owner_id": model.owner_id,
            "collection_id": model.collection_id,
            "title": model.title,
            "created_at": self._serialize_datetime(model.created_at),
            "updated_at": self._serialize_datetime(model.updated_at),
        }

    def _message_to_dict(self, model: MessageModel) -> dict:
        return {
            "id": model.id,
            "conversation_id": model.conversation_id,
            "role": model.role,
            "content": model.content,
            "sources": model.sources or [],
            "token_usage": model.token_usage,
            "created_at": self._serialize_datetime(model.created_at),
        }

    def get_or_create(
        self,
        conversation_id: str | None,
        collection_id: str,
        owner_id: str,
        title: str | None = None,
    ) -> dict:
        with self.session_factory() as session:
            if conversation_id:
                conversation = session.scalar(
                    select(ConversationModel).where(
                        ConversationModel.id == conversation_id,
                        ConversationModel.owner_id == owner_id,
                    )
                )
                if conversation:
                    return self._conversation_to_dict(conversation)

            conversation = ConversationModel(
                id=conversation_id,
                owner_id=owner_id,
                collection_id=collection_id,
                title=title,
            )
            session.add(conversation)
            session.commit()
            session.refresh(conversation)
            return self._conversation_to_dict(conversation)

    def list_conversations(self, owner_id: str, collection_id: str | None = None) -> list[dict]:
        with self.session_factory() as session:
            query = select(ConversationModel).where(ConversationModel.owner_id == owner_id)
            if collection_id is not None:
                query = query.where(ConversationModel.collection_id == collection_id)
            items = session.scalars(query.order_by(desc(ConversationModel.updated_at))).all()
            return [self._conversation_to_dict(item) for item in items]

    def get(self, conversation_id: str, owner_id: str | None = None) -> dict | None:
        with self.session_factory() as session:
            query = select(ConversationModel).where(ConversationModel.id == conversation_id)
            if owner_id is not None:
                query = query.where(ConversationModel.owner_id == owner_id)
            item = session.scalar(query)
            return self._conversation_to_dict(item) if item else None

    def list_messages(self, conversation_id: str) -> list[dict]:
        with self.session_factory() as session:
            items = session.scalars(
                select(MessageModel)
                .where(MessageModel.conversation_id == conversation_id)
                .order_by(MessageModel.created_at.asc())
            ).all()
            return [self._message_to_dict(item) for item in items]

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        sources: list[dict] | None = None,
        token_usage: dict | None = None,
    ) -> dict:
        with self.session_factory() as session:
            item = MessageModel(
                conversation_id=conversation_id,
                role=role,
                content=content,
                sources=sources or [],
                token_usage=token_usage,
            )
            session.add(item)

            conversation = session.get(ConversationModel, conversation_id)
            if conversation:
                conversation.updated_at = conversation_utc_now()

            session.commit()
            session.refresh(item)
            return self._message_to_dict(item)
