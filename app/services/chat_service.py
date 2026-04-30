from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.exceptions import BadRequestError, NotFoundError, ServiceUnavailableError
from app.rag.prompts import build_system_prompt
from app.repositories.conversation_repository import ConversationRepository
from app.schemas.chat import ChatRequest, ChatResponse, SourceDocument
from app.services.collection_service import CollectionService
from app.services.retrieval_service import RetrievalService


class ChatService:
    def __init__(
        self,
        settings: Settings,
        collection_service: CollectionService,
        conversation_repository: ConversationRepository,
        retrieval_service: RetrievalService,
    ):
        self.settings = settings
        self.collection_service = collection_service
        self.conversation_repository = conversation_repository
        self.retrieval_service = retrieval_service
        self._llm = None

    def _get_llm(self) -> ChatOpenAI:
        if self._llm is None:
            if not self.settings.openai_api_key:
                raise ServiceUnavailableError(
                    code="OPENAI_API_KEY_MISSING",
                    message="OPENAI_API_KEY is required for chat completion.",
                )

            self._llm = ChatOpenAI(
                model=self.settings.openai_model,
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                temperature=0,
                timeout=60,
                max_retries=2,
            )
        return self._llm

    def _normalize_content(self, content) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    parts.append(str(item["text"]))
                else:
                    parts.append(str(item))
            return "\n".join(parts)
        return str(content)

    def _build_sources(self, retrieved_chunks) -> list[SourceDocument]:
        return [
            SourceDocument(
                document_id=chunk.document_id,
                chunk_id=chunk.chunk_id,
                source_name=chunk.source_name,
                source_path=chunk.source_path,
                chunk_index=chunk.chunk_index,
                score=chunk.score,
                content=chunk.content,
            )
            for chunk in retrieved_chunks
        ]

    def _build_messages(
        self,
        *,
        history: list[dict],
        context: str,
        query: str,
    ) -> list:
        messages = [SystemMessage(content=build_system_prompt(context))]
        for item in history[-10:]:
            if item["role"] == "assistant":
                messages.append(AIMessage(content=item["content"]))
            else:
                messages.append(HumanMessage(content=item["content"]))
        messages.append(HumanMessage(content=query))
        return messages

    def _use_query_rewrite(self, payload: ChatRequest) -> bool:
        if payload.use_query_rewrite is None:
            return self.settings.rag_query_rewrite_enabled
        return payload.use_query_rewrite

    def _rewrite_query_for_retrieval(
        self,
        *,
        history: list[dict],
        query: str,
        payload: ChatRequest,
    ) -> str:
        if not self._use_query_rewrite(payload):
            return query
        if not history:
            return query

        history_window = history[-self.settings.rag_query_rewrite_history_messages :]
        history_lines = [
            f"{item['role']}: {self._normalize_content(item['content'])}"
            for item in history_window
        ]

        rewrite_messages = [
            SystemMessage(
                content=(
                    "You rewrite follow-up questions for retrieval. "
                    "Return one concise standalone search query only. "
                    "Preserve names, numbers, dates, acronyms, and product terms. "
                    "Do not answer the question."
                )
            ),
            HumanMessage(
                content=(
                    "Conversation history:\n"
                    f"{chr(10).join(history_lines)}\n\n"
                    "Latest user question:\n"
                    f"{query}\n\n"
                    "Standalone retrieval query:"
                )
            ),
        ]

        try:
            rewritten = self._normalize_content(self._get_llm().invoke(rewrite_messages).content).strip()
        except Exception:
            return query

        if not rewritten:
            return query
        return rewritten[: self.settings.rag_query_rewrite_max_chars]

    def _prepare_chat(self, payload: ChatRequest, owner_id: str) -> dict[str, Any]:
        self.collection_service.get_collection(payload.collection_id, owner_id=owner_id)

        try:
            conversation = self.conversation_repository.get_or_create(
                conversation_id=payload.conversation_id,
                collection_id=payload.collection_id,
                owner_id=owner_id,
                title=payload.query[:60],
            )
        except IntegrityError as exc:
            if payload.conversation_id:
                raise NotFoundError(
                    code="CONVERSATION_NOT_FOUND",
                    message=f"Conversation '{payload.conversation_id}' not found.",
                ) from exc
            raise
        if conversation["collection_id"] != payload.collection_id:
            raise BadRequestError(
                code="CONVERSATION_COLLECTION_MISMATCH",
                message="The conversation does not belong to the requested collection.",
            )
        history = self.conversation_repository.list_messages(conversation["id"])
        retrieval_query = self._rewrite_query_for_retrieval(
            history=history,
            query=payload.query,
            payload=payload,
        )
        retrieved_chunks = self.retrieval_service.retrieve(
            query=retrieval_query,
            collection_id=payload.collection_id,
            top_k=payload.top_k,
            use_hybrid_search=payload.use_hybrid_search,
            use_rerank=payload.use_rerank,
        )
        sources = self._build_sources(retrieved_chunks)
        context = "\n\n".join(
            f"[{index + 1}] {chunk.source_name}\n{chunk.content}"
            for index, chunk in enumerate(retrieved_chunks)
        )[: self.settings.rag_max_context_chars]
        messages = self._build_messages(history=history, context=context, query=payload.query)
        return {
            "conversation": conversation,
            "messages": messages,
            "retrieval_query": retrieval_query,
            "sources": sources,
        }

    def _extract_token_usage(self, response) -> dict | None:
        response_metadata = getattr(response, "response_metadata", {}) or {}
        token_usage = response_metadata.get("token_usage")
        if token_usage:
            return token_usage
        usage_metadata = getattr(response, "usage_metadata", None)
        if usage_metadata:
            return dict(usage_metadata)
        return None

    def _persist_user_message(self, conversation_id: str, query: str) -> None:
        self.conversation_repository.add_message(
            conversation_id=conversation_id,
            role="user",
            content=query,
        )

    def _persist_assistant_message(
        self,
        *,
        conversation_id: str,
        answer: str,
        sources: list[SourceDocument],
        token_usage: dict | None,
    ) -> None:
        self.conversation_repository.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=answer,
            sources=[source.model_dump() for source in sources],
            token_usage=token_usage,
        )

    def chat(self, payload: ChatRequest, owner_id: str) -> ChatResponse:
        prepared = self._prepare_chat(payload, owner_id)
        conversation = prepared["conversation"]
        messages = prepared["messages"]
        sources = prepared["sources"]

        response = self._get_llm().invoke(messages)
        answer = self._normalize_content(response.content)
        token_usage = self._extract_token_usage(response)

        self._persist_user_message(conversation["id"], payload.query)
        self._persist_assistant_message(
            conversation_id=conversation["id"],
            answer=answer,
            sources=sources,
            token_usage=token_usage,
        )

        return ChatResponse(
            answer=answer,
            conversation_id=conversation["id"],
            sources=sources,
            token_usage=token_usage,
        )

    def stream_chat(self, payload: ChatRequest, owner_id: str) -> Iterator[dict]:
        prepared = self._prepare_chat(payload, owner_id)
        conversation = prepared["conversation"]
        messages = prepared["messages"]
        sources = prepared["sources"]
        serialized_sources = [source.model_dump() for source in sources]
        llm = self._get_llm()

        self._persist_user_message(conversation["id"], payload.query)

        def event_stream() -> Iterator[dict]:
            answer_parts: list[str] = []
            token_usage: dict | None = None

            yield {
                "event": "start",
                "data": {
                    "conversation_id": conversation["id"],
                },
            }

            try:
                for chunk in llm.stream(messages):
                    token_usage = self._extract_token_usage(chunk) or token_usage
                    delta = self._normalize_content(chunk.content)
                    if not delta:
                        continue
                    answer_parts.append(delta)
                    yield {
                        "event": "token",
                        "data": {
                            "delta": delta,
                        },
                    }

                answer = "".join(answer_parts)
                self._persist_assistant_message(
                    conversation_id=conversation["id"],
                    answer=answer,
                    sources=sources,
                    token_usage=token_usage,
                )
                yield {
                    "event": "sources",
                    "data": {
                        "conversation_id": conversation["id"],
                        "sources": serialized_sources,
                        "token_usage": token_usage,
                    },
                }
                yield {
                    "event": "done",
                    "data": {
                        "conversation_id": conversation["id"],
                        "answer": answer,
                    },
                }
            except Exception as exc:
                yield {
                    "event": "error",
                    "data": {
                        "code": "STREAM_GENERATION_ERROR",
                        "message": str(exc),
                    },
                }

        return event_stream()
