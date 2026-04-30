from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from starlette.datastructures import UploadFile

from app.core.path_utils import normalize_document_storage_path, resolve_document_storage_path
from app.services.document_service import DocumentService
from app.services.ingestion_service import IngestionService


class FakeCollectionService:
    def get_collection(self, collection_id: str, owner_id: str) -> dict:
        return {"id": collection_id, "owner_id": owner_id}


class FakeDocumentRepository:
    def __init__(self) -> None:
        self.items: dict[str, dict] = {}

    def save(self, record: dict) -> dict:
        self.items[record["id"]] = dict(record)
        return dict(record)

    def touch(self, document_id: str, **updates) -> dict | None:
        item = self.items.get(document_id)
        if not item:
            return None
        item.update(updates)
        return dict(item)

    def get(self, document_id: str, owner_id: str | None = None) -> dict | None:
        item = self.items.get(document_id)
        if not item:
            return None
        if owner_id is not None and item.get("owner_id") != owner_id:
            return None
        return dict(item)

    def list_documents(self, collection_id: str | None = None, owner_id: str | None = None) -> list[dict]:
        results = []
        for item in self.items.values():
            if collection_id is not None and item["collection_id"] != collection_id:
                continue
            if owner_id is not None and item.get("owner_id") != owner_id:
                continue
            results.append(dict(item))
        return results


class FakeTaskQueueService:
    def enqueue_document_ingestion(self, document_id: str) -> str:
        return f"task-{document_id}"


class FakeVectorStoreService:
    def delete_by_document_id(self, collection_id: str, document_id: str) -> int:
        return 1

    def list_document_chunks(self, collection_id: str, document_id: str, limit: int | None = None) -> list:
        return []

    def add_documents(self, collection_id: str, chunks: list) -> int:
        return len(chunks)


def build_settings(data_dir: Path) -> SimpleNamespace:
    raw_data_dir = data_dir / "raw"
    processed_data_dir = data_dir / "processed"
    faiss_index_dir = data_dir / "faiss_indexes"
    raw_data_dir.mkdir(parents=True, exist_ok=True)
    processed_data_dir.mkdir(parents=True, exist_ok=True)
    faiss_index_dir.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(
        data_dir=data_dir,
        raw_data_dir=raw_data_dir,
        processed_data_dir=processed_data_dir,
        faiss_index_dir=faiss_index_dir,
        upload_max_bytes=1024 * 1024,
        allowed_extensions={"txt", "pdf", "doc", "docx"},
        rag_chunk_size=500,
        rag_chunk_overlap=80,
    )


def test_normalize_and_resolve_legacy_windows_document_path(tmp_path: Path) -> None:
    settings = build_settings(tmp_path / "data")
    legacy_path = r"D:\Dify\LangChain\ChatRobot_v3\data\raw\legacy-handbook.pdf"

    normalized = normalize_document_storage_path(legacy_path, settings)
    resolved = resolve_document_storage_path(legacy_path, settings)

    assert normalized == "raw/legacy-handbook.pdf"
    assert resolved == settings.data_dir / "raw/legacy-handbook.pdf"


def test_upload_document_stores_relative_path_for_new_records(tmp_path: Path) -> None:
    repository = FakeDocumentRepository()
    settings = build_settings(tmp_path / "data")
    service = DocumentService(
        settings=settings,
        collection_service=FakeCollectionService(),
        document_repository=repository,
        ingestion_service=None,
        task_queue_service=FakeTaskQueueService(),
        vector_store_service=FakeVectorStoreService(),
    )

    async def run_upload() -> dict:
        upload = UploadFile(filename="handbook.txt", file=BytesIO(b"hello knowledge base"))
        return await service.upload_document(upload, collection_id="collection-1", owner_id="user-1")

    result = asyncio.run(run_upload())

    assert result["file_path"].startswith("raw/")
    saved = repository.items[result["id"]]
    assert saved["file_path"].startswith("raw/")
    assert (settings.data_dir / saved["file_path"]).exists()


def test_ingestion_service_resolves_legacy_path_but_indexes_portable_source_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repository = FakeDocumentRepository()
    repository.items["document-1"] = {
        "id": "document-1",
        "owner_id": "user-1",
        "collection_id": "collection-1",
        "filename": "legacy.txt",
        "file_path": r"D:\Dify\LangChain\ChatRobot_v3\data\raw\legacy.txt",
        "file_type": "txt",
        "file_size": 32,
        "status": "uploaded",
        "chunk_count": 0,
        "error_message": None,
        "created_at": "2026-04-28T00:00:00+00:00",
        "updated_at": "2026-04-28T00:00:00+00:00",
    }

    settings = build_settings(tmp_path / "data")
    captured: dict[str, object] = {}

    def fake_load_documents_from_path(file_path: Path) -> list[object]:
        captured["loaded_path"] = file_path
        return ["loaded"]

    def fake_split_documents(
        loaded_documents,
        *,
        collection_id: str,
        document_id: str,
        source_name: str,
        source_path: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[dict]:
        captured["split_source_path"] = source_path
        return [{"chunk_id": "chunk-1"}]

    monkeypatch.setattr("app.services.ingestion_service.load_documents_from_path", fake_load_documents_from_path)
    monkeypatch.setattr("app.services.ingestion_service.split_documents", fake_split_documents)

    service = IngestionService(
        settings=settings,
        document_repository=repository,
        vector_store_service=FakeVectorStoreService(),
    )

    result = service.ingest_document("document-1")

    assert captured["loaded_path"] == settings.data_dir / "raw/legacy.txt"
    assert captured["split_source_path"] == "raw/legacy.txt"
    assert result["status"] == "indexed"
