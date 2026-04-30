from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    app_name: str
    environment: str
    vector_backend: str
    documents_dir: str
    indexes_dir: str


class DocumentChunk(BaseModel):
    document_id: str
    collection_id: str
    chunk_id: str
    chunk_index: int
    chunk_text: str
    source_name: str
    source_path: str
    metadata: dict = Field(default_factory=dict)
