from app.core.exceptions import NotFoundError
from app.services.conversation_service import ConversationService


class FakeConversationRepository:
    def list_conversations(self, owner_id: str, collection_id: str | None = None) -> list[dict]:
        return [
            {
                "id": "conversation-1",
                "owner_id": owner_id,
                "collection_id": collection_id or "collection-1",
                "title": "请假流程",
                "created_at": "2026-04-28T00:00:00+00:00",
                "updated_at": "2026-04-28T00:10:00+00:00",
            }
        ]

    def get(self, conversation_id: str, owner_id: str | None = None) -> dict | None:
        if conversation_id != "conversation-1" or owner_id != "user-1":
            return None
        return {
            "id": "conversation-1",
            "owner_id": "user-1",
            "collection_id": "collection-1",
            "title": "请假流程",
            "created_at": "2026-04-28T00:00:00+00:00",
            "updated_at": "2026-04-28T00:10:00+00:00",
        }

    def list_messages(self, conversation_id: str) -> list[dict]:
        return [
            {
                "id": "message-1",
                "conversation_id": conversation_id,
                "role": "user",
                "content": "请假怎么申请？",
                "sources": [],
                "token_usage": None,
                "created_at": "2026-04-28T00:00:00+00:00",
            }
        ]


def test_list_conversations_returns_repository_data() -> None:
    service = ConversationService(FakeConversationRepository())

    conversations = service.list_conversations(owner_id="user-1", collection_id="collection-1")

    assert conversations[0]["id"] == "conversation-1"
    assert conversations[0]["collection_id"] == "collection-1"


def test_get_conversation_detail_returns_messages() -> None:
    service = ConversationService(FakeConversationRepository())

    detail = service.get_conversation_detail("conversation-1", owner_id="user-1")

    assert detail["id"] == "conversation-1"
    assert detail["messages"][0]["content"] == "请假怎么申请？"


def test_get_conversation_detail_rejects_other_users_conversation() -> None:
    service = ConversationService(FakeConversationRepository())

    try:
        service.get_conversation_detail("conversation-1", owner_id="user-2")
    except NotFoundError as exc:
        assert exc.code == "CONVERSATION_NOT_FOUND"
    else:
        raise AssertionError("Expected NotFoundError for foreign conversation access")
