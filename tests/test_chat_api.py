from fastapi.testclient import TestClient

from app.api.deps import get_chat_service, get_current_user
from app.main import create_app


class FakeChatService:
    def chat(self, payload, owner_id: str):
        assert owner_id == "user-1"
        assert payload.stream is False
        return {
            "answer": "完整回答",
            "conversation_id": "conversation-1",
            "sources": [],
            "token_usage": {"total_tokens": 12},
        }

    def stream_chat(self, payload, owner_id: str):
        assert owner_id == "user-1"
        assert payload.stream is True
        yield {
            "event": "start",
            "data": {
                "conversation_id": "conversation-1",
            },
        }
        yield {
            "event": "token",
            "data": {
                "delta": "你好",
            },
        }
        yield {
            "event": "token",
            "data": {
                "delta": "，世界",
            },
        }
        yield {
            "event": "sources",
            "data": {
                "conversation_id": "conversation-1",
                "sources": [
                    {
                        "document_id": "doc-1",
                        "chunk_id": "chunk-1",
                        "source_name": "员工手册",
                        "source_path": "docs/employee-handbook.pdf",
                        "chunk_index": 0,
                        "score": 0.98,
                        "content": "这里是引用内容。",
                    }
                ],
                "token_usage": {"total_tokens": 12},
            },
        }
        yield {
            "event": "done",
            "data": {
                "conversation_id": "conversation-1",
                "answer": "你好，世界",
            },
        }


def build_client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"id": "user-1", "username": "alice"}
    app.dependency_overrides[get_chat_service] = lambda: FakeChatService()
    return TestClient(app)


def test_chat_completion_returns_json_response() -> None:
    client = build_client()

    response = client.post(
        "/api/v1/chat/completions",
        json={
            "query": "你好",
            "collection_id": "collection-1",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "完整回答"
    assert payload["conversation_id"] == "conversation-1"


def test_chat_completion_returns_sse_stream() -> None:
    client = build_client()

    response = client.post(
        "/api/v1/chat/completions",
        json={
            "query": "你好",
            "collection_id": "collection-1",
            "stream": True,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: start" in response.text
    assert "event: token" in response.text
    assert "event: sources" in response.text
    assert '"answer": "你好，世界"' in response.text
