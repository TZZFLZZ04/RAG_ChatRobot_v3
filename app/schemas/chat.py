from pydantic import BaseModel, Field


class SourceDocument(BaseModel):
    document_id: str
    chunk_id: str
    source_name: str
    source_path: str
    chunk_index: int
    score: float | None = None
    content: str


class RetrievedChunk(SourceDocument):
    metadata: dict = Field(default_factory=dict)


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None
    collection_id: str
    top_k: int = Field(default=5, ge=1, le=20)
    use_hybrid_search: bool | None = None
    use_rerank: bool | None = None
    use_query_rewrite: bool | None = None
    stream: bool = False


class ChatResponse(BaseModel):
    answer: str
    conversation_id: str
    sources: list[SourceDocument]
    token_usage: dict | None = None


class ConversationMessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    sources: list[SourceDocument] = Field(default_factory=list)
    token_usage: dict | None = None
    created_at: str


class ConversationSummaryResponse(BaseModel):
    id: str
    collection_id: str
    title: str | None = None
    created_at: str
    updated_at: str


class ConversationDetailResponse(ConversationSummaryResponse):
    messages: list[ConversationMessageResponse]
