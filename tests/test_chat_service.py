from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import BadRequestError, NotFoundError
from app.schemas.chat import ChatRequest, RetrievedChunk
from app.services.chat_service import ChatService


class FakeCollectionService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def get_collection(self, collection_id: str, owner_id: str) -> dict:
        self.calls.append((collection_id, owner_id))
        return {"id": collection_id, "owner_id": owner_id}


class FakeConversationRepository:
    def __init__(self, conversation=None, error: Exception | None = None, history=None) -> None:
        self.conversation = conversation
        self.error = error
        self.history = history or []
        self.messages_added: list[tuple[str, str, str]] = []

    def get_or_create(self, conversation_id: str | None, collection_id: str, owner_id: str, title: str | None = None) -> dict:
        if self.error:
            raise self.error
        if self.conversation is not None:
            return self.conversation
        return {
            "id": conversation_id or "conversation-1",
            "owner_id": owner_id,
            "collection_id": collection_id,
            "title": title,
        }

    def list_messages(self, conversation_id: str) -> list[dict]:
        return list(self.history)

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        sources: list[dict] | None = None,
        token_usage: dict | None = None,
    ) -> dict:
        self.messages_added.append((conversation_id, role, content))
        return {
            "id": f"message-{len(self.messages_added)}",
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "sources": sources or [],
            "token_usage": token_usage,
            "created_at": "2026-04-28T00:00:00+00:00",
        }


class FakeRetrievalService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def retrieve(
        self,
        query: str,
        collection_id: str,
        top_k: int,
        use_hybrid_search: bool | None = None,
        use_rerank: bool | None = None,
    ):
        self.calls.append(
            {
                "query": query,
                "collection_id": collection_id,
                "top_k": top_k,
                "use_hybrid_search": use_hybrid_search,
                "use_rerank": use_rerank,
            }
        )
        return [
            RetrievedChunk(
                document_id="document-1",
                chunk_id="chunk-1",
                source_name="handbook.pdf",
                source_path="data/raw/handbook.pdf",
                chunk_index=0,
                score=0.95,
                content="Team handbook content",
                metadata={"page": 1},
            )
        ]


class FakeLLM:
    def __init__(self) -> None:
        self.invocations = []

    def invoke(self, messages):
        self.invocations.append(messages)
        if "Standalone retrieval query:" in str(messages[-1].content):
            return SimpleNamespace(content="2026年员工请假制度")
        return SimpleNamespace(
            content="answer",
            response_metadata={"token_usage": {"total_tokens": 12}},
        )


def build_service(
    *,
    conversation=None,
    error: Exception | None = None,
    history=None,
) -> tuple[ChatService, FakeCollectionService, FakeConversationRepository, FakeRetrievalService]:
    collection_service = FakeCollectionService()
    conversation_repository = FakeConversationRepository(
        conversation=conversation,
        error=error,
        history=history,
    )
    retrieval_service = FakeRetrievalService()
    settings = SimpleNamespace(
        openai_api_key="test-key",
        openai_model="gpt-4o-mini",
        openai_base_url="https://example.com/v1",
        rag_max_context_chars=4000,
        rag_query_rewrite_enabled=True,
        rag_query_rewrite_history_messages=6,
        rag_query_rewrite_max_chars=300,
    )
    service = ChatService(
        settings=settings,
        collection_service=collection_service,
        conversation_repository=conversation_repository,
        retrieval_service=retrieval_service,
    )
    service._llm = FakeLLM()
    return service, collection_service, conversation_repository, retrieval_service


def test_chat_service_uses_owner_scope_for_collection_lookup() -> None:
    service, collection_service, conversation_repository, _retrieval_service = build_service()

    response = service.chat(
        ChatRequest(query="hello", collection_id="collection-1"),
        owner_id="user-1",
    )

    assert collection_service.calls == [("collection-1", "user-1")]
    assert response.conversation_id == "conversation-1"
    assert [role for _conversation_id, role, _content in conversation_repository.messages_added] == [
        "user",
        "assistant",
    ]


def test_chat_service_rejects_conversation_collection_mismatch() -> None:
    service, _collection_service, _conversation_repository, _retrieval_service = build_service(
        conversation={
            "id": "conversation-1",
            "owner_id": "user-1",
            "collection_id": "collection-2",
            "title": "existing",
        }
    )

    with pytest.raises(BadRequestError) as exc_info:
        service.chat(
            ChatRequest(
                query="hello",
                collection_id="collection-1",
                conversation_id="conversation-1",
            ),
            owner_id="user-1",
        )

    assert exc_info.value.code == "CONVERSATION_COLLECTION_MISMATCH"


def test_chat_service_hides_other_users_conversation_id() -> None:
    service, _collection_service, _conversation_repository, _retrieval_service = build_service(
        error=IntegrityError("insert into conversations", params={}, orig=Exception("duplicate key"))
    )

    with pytest.raises(NotFoundError) as exc_info:
        service.chat(
            ChatRequest(
                query="hello",
                collection_id="collection-1",
                conversation_id="conversation-foreign",
            ),
            owner_id="user-1",
        )

    assert exc_info.value.code == "CONVERSATION_NOT_FOUND"


def test_chat_service_rewrites_follow_up_query_for_retrieval() -> None:
    service, _collection_service, _conversation_repository, retrieval_service = build_service(
        history=[
            {"role": "user", "content": "请总结 2026 年员工手册"},
            {"role": "assistant", "content": "已经总结了员工手册。"},
        ]
    )

    response = service.chat(
        ChatRequest(
            query="请假制度呢？",
            collection_id="collection-1",
            use_query_rewrite=True,
            use_hybrid_search=True,
            use_rerank=True,
        ),
        owner_id="user-1",
    )

    assert response.answer == "answer"
    assert retrieval_service.calls == [
        {
            "query": "2026年员工请假制度",
            "collection_id": "collection-1",
            "top_k": 5,
            "use_hybrid_search": True,
            "use_rerank": True,
        }
    ]
    assert service._llm.invocations[-1][-1].content == "请假制度呢？"
