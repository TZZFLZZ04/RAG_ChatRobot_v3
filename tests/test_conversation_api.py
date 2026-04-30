from fastapi.testclient import TestClient

from app.api.deps import get_conversation_service, get_current_user
from app.core.exceptions import NotFoundError
from app.main import create_app


class FakeConversationService:
    def list_conversations(self, owner_id: str, collection_id: str | None = None) -> list[dict]:
        assert owner_id == "user-1"
        assert collection_id == "collection-1"
        return [
            {
                "id": "conversation-1",
                "collection_id": "collection-1",
                "title": "请假流程",
                "created_at": "2026-04-28T00:00:00+00:00",
                "updated_at": "2026-04-28T00:10:00+00:00",
            }
        ]

    def get_conversation_detail(self, conversation_id: str, owner_id: str) -> dict:
        assert owner_id == "user-1"
        if conversation_id != "conversation-1":
            raise NotFoundError(
                code="CONVERSATION_NOT_FOUND",
                message=f"Conversation '{conversation_id}' not found.",
            )
        return {
            "id": "conversation-1",
            "collection_id": "collection-1",
            "title": "请假流程",
            "created_at": "2026-04-28T00:00:00+00:00",
            "updated_at": "2026-04-28T00:10:00+00:00",
            "messages": [
                {
                    "id": "message-1",
                    "conversation_id": "conversation-1",
                    "role": "user",
                    "content": "请假怎么申请？",
                    "sources": [],
                    "token_usage": None,
                    "created_at": "2026-04-28T00:00:00+00:00",
                },
                {
                    "id": "message-2",
                    "conversation_id": "conversation-1",
                    "role": "assistant",
                    "content": "先在系统里提交审批。",
                    "sources": [
                        {
                            "document_id": "doc-1",
                            "chunk_id": "chunk-1",
                            "source_name": "员工手册",
                            "source_path": "raw/handbook.pdf",
                            "chunk_index": 0,
                            "score": 0.98,
                            "content": "请假审批流程说明",
                        }
                    ],
                    "token_usage": {"total_tokens": 18},
                    "created_at": "2026-04-28T00:00:05+00:00",
                },
            ],
        }


def build_client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"id": "user-1", "username": "alice"}
    app.dependency_overrides[get_conversation_service] = lambda: FakeConversationService()
    return TestClient(app)


def test_list_conversations_returns_current_user_history() -> None:
    client = build_client()

    response = client.get("/api/v1/conversations", params={"collection_id": "collection-1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload == [
        {
            "id": "conversation-1",
            "collection_id": "collection-1",
            "title": "请假流程",
            "created_at": "2026-04-28T00:00:00+00:00",
            "updated_at": "2026-04-28T00:10:00+00:00",
        }
    ]


def test_get_conversation_detail_returns_messages() -> None:
    client = build_client()

    response = client.get("/api/v1/conversations/conversation-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "conversation-1"
    assert len(payload["messages"]) == 2
    assert payload["messages"][1]["sources"][0]["source_name"] == "员工手册"


def test_get_conversation_detail_hides_other_users_conversations() -> None:
    client = build_client()

    response = client.get("/api/v1/conversations/conversation-2")

    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "CONVERSATION_NOT_FOUND"
