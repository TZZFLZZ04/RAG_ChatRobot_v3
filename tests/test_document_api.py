from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_document_service
from app.core.exceptions import NotFoundError
from app.main import create_app


class FakeDocumentService:
    async def upload_document(self, upload, collection_id: str, owner_id: str) -> dict:
        assert collection_id == "collection-1"
        assert owner_id == "user-1"
        assert upload.filename == "handbook.txt"
        content = await upload.read()
        assert content == b"hello knowledge base"
        await upload.close()
        return {
            "id": "document-1",
            "collection_id": collection_id,
            "filename": upload.filename,
            "file_path": "data/raw/document-1_handbook.txt",
            "file_type": "txt",
            "file_size": len(content),
            "status": "queued",
            "chunk_count": 0,
            "error_message": None,
            "created_at": "2026-04-28T00:00:00+00:00",
            "updated_at": "2026-04-28T00:00:00+00:00",
            "task_id": "task-1",
            "task_status": "queued",
        }

    def list_documents(self, owner_id: str, collection_id: str | None = None) -> list[dict]:
        assert owner_id == "user-1"
        assert collection_id == "collection-1"
        return [
            {
                "id": "document-1",
                "collection_id": "collection-1",
                "filename": "handbook.pdf",
                "file_path": "data/raw/document-1_handbook.pdf",
                "file_type": "pdf",
                "file_size": 1024,
                "status": "indexed",
                "chunk_count": 2,
                "error_message": None,
                "created_at": "2026-04-28T00:00:00+00:00",
                "updated_at": "2026-04-28T00:00:00+00:00",
            }
        ]

    def get_document_detail(self, document_id: str, owner_id: str) -> dict:
        assert document_id == "document-1"
        assert owner_id == "user-1"
        return {
            "id": "document-1",
            "collection_id": "collection-1",
            "filename": "handbook.pdf",
            "file_path": "data/raw/document-1_handbook.pdf",
            "file_type": "pdf",
            "file_size": 1024,
            "status": "indexed",
            "chunk_count": 2,
            "error_message": None,
            "created_at": "2026-04-28T00:00:00+00:00",
            "updated_at": "2026-04-28T00:00:00+00:00",
            "chunk_preview": [
                {
                    "chunk_id": "document-1-0",
                    "chunk_index": 0,
                    "content": "第一页内容",
                    "source_name": "handbook.pdf",
                    "source_path": "data/raw/document-1_handbook.pdf",
                    "metadata": {"page": 1},
                }
            ],
            "chunk_preview_error": None,
            "preview_limit": 20,
        }

    def retry_document(self, document_id: str, owner_id: str) -> dict:
        assert document_id == "document-1"
        assert owner_id == "user-1"
        return {
            "id": "document-1",
            "collection_id": "collection-1",
            "filename": "handbook.pdf",
            "file_path": "data/raw/document-1_handbook.pdf",
            "file_type": "pdf",
            "file_size": 1024,
            "status": "queued",
            "chunk_count": 0,
            "error_message": None,
            "created_at": "2026-04-28T00:00:00+00:00",
            "updated_at": "2026-04-28T00:00:00+00:00",
            "task_id": "task-1",
            "task_status": "queued",
        }

    def delete_document(self, document_id: str, owner_id: str) -> dict:
        assert document_id == "document-1"
        assert owner_id == "user-1"
        return {
            "id": "document-1",
            "collection_id": "collection-1",
            "filename": "handbook.pdf",
            "file_path": "data/raw/document-1_handbook.pdf",
            "file_type": "pdf",
            "file_size": 1024,
            "status": "deleted",
            "chunk_count": 2,
            "error_message": None,
            "created_at": "2026-04-28T00:00:00+00:00",
            "updated_at": "2026-04-28T00:00:00+00:00",
        }


class MissingDocumentService:
    def get_document_detail(self, document_id: str, owner_id: str) -> dict:
        raise NotFoundError(
            code="DOCUMENT_NOT_FOUND",
            message=f"Document '{document_id}' not found.",
        )

    def retry_document(self, document_id: str, owner_id: str) -> dict:
        raise NotFoundError(
            code="DOCUMENT_NOT_FOUND",
            message=f"Document '{document_id}' not found.",
        )

    def delete_document(self, document_id: str, owner_id: str) -> dict:
        raise NotFoundError(
            code="DOCUMENT_NOT_FOUND",
            message=f"Document '{document_id}' not found.",
        )


def build_client(document_service=None) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {"id": "user-1", "username": "alice"}
    app.dependency_overrides[get_document_service] = lambda: document_service or FakeDocumentService()
    return TestClient(app)


def test_upload_document_uses_current_user_scope() -> None:
    client = build_client()

    response = client.post(
        "/api/v1/documents/upload",
        data={"collection_id": "collection-1"},
        files={"file": ("handbook.txt", b"hello knowledge base", "text/plain")},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["collection_id"] == "collection-1"
    assert payload["task_id"] == "task-1"


def test_list_documents_returns_collection_scoped_results() -> None:
    client = build_client()

    response = client.get("/api/v1/documents", params={"collection_id": "collection-1"})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == "document-1"


def test_get_document_detail_returns_chunk_preview() -> None:
    client = build_client()

    response = client.get("/api/v1/documents/document-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "document-1"
    assert payload["chunk_preview"][0]["chunk_id"] == "document-1-0"
    assert payload["preview_limit"] == 20


def test_retry_document_returns_queued_task() -> None:
    client = build_client()

    response = client.post("/api/v1/documents/document-1/retry")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["task_id"] == "task-1"


def test_delete_document_uses_current_user_scope() -> None:
    client = build_client()

    response = client.delete("/api/v1/documents/document-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "deleted"


def test_document_detail_hides_other_users_documents() -> None:
    client = build_client(document_service=MissingDocumentService())

    response = client.get("/api/v1/documents/document-2")

    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "DOCUMENT_NOT_FOUND"


def test_retry_document_hides_other_users_documents() -> None:
    client = build_client(document_service=MissingDocumentService())

    response = client.post("/api/v1/documents/document-2/retry")

    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "DOCUMENT_NOT_FOUND"


def test_delete_document_hides_other_users_documents() -> None:
    client = build_client(document_service=MissingDocumentService())

    response = client.delete("/api/v1/documents/document-2")

    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "DOCUMENT_NOT_FOUND"
