from pydantic import BaseModel, Field


class DocumentResponse(BaseModel):
    id: str
    collection_id: str
    filename: str
    file_path: str
    file_type: str
    file_size: int
    status: str
    chunk_count: int = 0
    error_message: str | None = None
    created_at: str
    updated_at: str


class DocumentTaskResponse(DocumentResponse):
    task_id: str | None = None
    task_status: str | None = None


class DocumentUploadResponse(DocumentTaskResponse):
    pass


class DocumentRetryResponse(DocumentTaskResponse):
    pass


class DocumentChunkPreviewResponse(BaseModel):
    chunk_id: str
    chunk_index: int
    content: str
    source_name: str
    source_path: str
    metadata: dict = Field(default_factory=dict)


class DocumentDetailResponse(DocumentResponse):
    chunk_preview: list[DocumentChunkPreviewResponse] = Field(default_factory=list)
    chunk_preview_error: str | None = None
    preview_limit: int = 20
