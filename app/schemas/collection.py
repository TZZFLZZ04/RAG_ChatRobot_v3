from pydantic import BaseModel, Field


class CollectionCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)


class CollectionResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    vector_backend: str
    created_at: str
    updated_at: str


class CollectionIngestResponse(BaseModel):
    collection_id: str
    queued_count: int
    task_ids: list[str] = Field(default_factory=list)
