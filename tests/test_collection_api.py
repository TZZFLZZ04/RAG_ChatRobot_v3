from fastapi.testclient import TestClient

from app.api.deps import get_collection_service, get_current_user, get_document_service
from app.core.exceptions import NotFoundError
from app.main import create_app


class FakeCollectionService:
    def create_collection(self, payload, owner_id: str) -> dict:
        assert owner_id == "user-1"
        assert payload.name == "team-kb"
        return {
            "id": "collection-1",
            "owner_id": owner_id,
            "name": payload.name,
            "description": payload.description,
            "vector_backend": "faiss",
            "created_at": "2026-04-28T00:00:00+00:00",
            "updated_at": "2026-04-28T00:00:00+00:00",
        }

    def list_collections(self, owner_id: str) -> list[dict]:
        assert owner_id == "user-1"
        return [
            {
                "id": "collection-1",
                "owner_id": owner_id,
                "name": "team-kb",
                "description": "shared docs",
                "vector_backend": "faiss",
                "created_at": "2026-04-28T00:00:00+00:00",
                "updated_at": "2026-04-28T00:00:00+00:00",
            }
        ]


class FakeDocumentService:
    def ingest_collection(self, collection_id: str, owner_id: str) -> dict:
        assert collection_id == "collection-1"
        assert owner_id == "user-1"
        return {
            "collection_id": collection_id,
            "queued_count": 2,
            "task_ids": ["task-1", "task-2"],
        }


class MissingCollectionDocumentService:
    def ingest_collection(self, collection_id: str, owner_id: str) -> dict:
        raise NotFoundError(
            code="COLLECTION_NOT_FOUND",
            message=f"Collection '{collection_id}' not found.",
        )


def build_client(document_service=None) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"id": "user-1", "username": "alice"}
    app.dependency_overrides[get_collection_service] = lambda: FakeCollectionService()
    app.dependency_overrides[get_document_service] = lambda: document_service or FakeDocumentService()
    return TestClient(app)


def test_create_collection_uses_current_user_scope() -> None:
    client = build_client()

    response = client.post(
        "/api/v1/collections",
        json={"name": "team-kb", "description": "shared docs"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["name"] == "team-kb"
    assert payload["vector_backend"] == "faiss"


def test_list_collections_returns_only_current_user_items() -> None:
    client = build_client()

    response = client.get("/api/v1/collections")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["name"] == "team-kb"


def test_ingest_collection_uses_current_user_scope() -> None:
    client = build_client()

    response = client.post("/api/v1/collections/collection-1/ingest")

    assert response.status_code == 200
    payload = response.json()
    assert payload["collection_id"] == "collection-1"
    assert payload["queued_count"] == 2


def test_ingest_collection_hides_other_users_collection() -> None:
    client = build_client(document_service=MissingCollectionDocumentService())

    response = client.post("/api/v1/collections/collection-2/ingest")

    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "COLLECTION_NOT_FOUND"
