from __future__ import annotations

from app.core.exceptions import NotFoundError
from app.repositories.conversation_repository import ConversationRepository


class ConversationService:
    def __init__(self, conversation_repository: ConversationRepository):
        self.conversation_repository = conversation_repository

    def list_conversations(self, owner_id: str, collection_id: str | None = None) -> list[dict]:
        return self.conversation_repository.list_conversations(owner_id=owner_id, collection_id=collection_id)

    def get_conversation_detail(self, conversation_id: str, owner_id: str) -> dict:
        conversation = self.conversation_repository.get(conversation_id, owner_id=owner_id)
        if not conversation:
            raise NotFoundError(
                code="CONVERSATION_NOT_FOUND",
                message=f"Conversation '{conversation_id}' not found.",
            )

        messages = self.conversation_repository.list_messages(conversation_id)
        return {
            **conversation,
            "messages": messages,
        }
