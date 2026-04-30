from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.exceptions import BadRequestError, NotFoundError
from app.db.models.collection import CollectionModel
from app.db.session import _ensure_collection_name_scope
from app.schemas.collection import CollectionCreateRequest
from app.services.collection_service import CollectionService


class FakeCollectionRepository:
    def __init__(self):
        self.items: list[dict] = []

    def get_by_name(self, name: str, owner_id: str | None = None) -> dict | None:
        for item in self.items:
            if item["name"] != name:
                continue
            if owner_id is None or item["owner_id"] == owner_id:
                return item
        return None

    def create_collection(
        self,
        *,
        owner_id: str,
        name: str,
        description: str | None,
        vector_backend: str,
    ) -> dict:
        record = {
            "id": f"collection-{len(self.items) + 1}",
            "owner_id": owner_id,
            "name": name,
            "description": description,
            "vector_backend": vector_backend,
            "created_at": "2026-04-28T00:00:00+00:00",
            "updated_at": "2026-04-28T00:00:00+00:00",
        }
        self.items.append(record)
        return record

    def list_collections(self, owner_id: str | None = None) -> list[dict]:
        if owner_id is None:
            return list(self.items)
        return [item for item in self.items if item["owner_id"] == owner_id]

    def get(self, record_id: str, owner_id: str | None = None) -> dict | None:
        for item in self.items:
            if item["id"] != record_id:
                continue
            if owner_id is None or item["owner_id"] == owner_id:
                return item
        return None


def create_collection_service() -> tuple[CollectionService, FakeCollectionRepository]:
    repository = FakeCollectionRepository()
    settings = SimpleNamespace(vector_backend="faiss")
    service = CollectionService(settings=settings, collection_repository=repository)
    return service, repository


def test_create_collection_rejects_duplicate_name_for_same_owner() -> None:
    service, _repository = create_collection_service()
    payload = CollectionCreateRequest(name="shared-kb", description="same owner")

    service.create_collection(payload, owner_id="user-1")

    with pytest.raises(BadRequestError) as exc_info:
        service.create_collection(payload, owner_id="user-1")

    assert exc_info.value.code == "COLLECTION_ALREADY_EXISTS"


def test_create_collection_allows_same_name_for_different_owners() -> None:
    service, repository = create_collection_service()
    payload = CollectionCreateRequest(name="shared-kb", description="cross user")

    first = service.create_collection(payload, owner_id="user-1")
    second = service.create_collection(payload, owner_id="user-2")

    assert first["name"] == second["name"] == "shared-kb"
    assert first["owner_id"] == "user-1"
    assert second["owner_id"] == "user-2"
    assert len(repository.items) == 2


def test_list_collections_returns_only_requested_owner_records() -> None:
    service, repository = create_collection_service()
    repository.items.extend(
        [
            {
                "id": "collection-1",
                "owner_id": "user-1",
                "name": "alice-kb",
                "description": "alice docs",
                "vector_backend": "faiss",
                "created_at": "2026-04-28T00:00:00+00:00",
                "updated_at": "2026-04-28T00:00:00+00:00",
            },
            {
                "id": "collection-2",
                "owner_id": "user-2",
                "name": "bob-kb",
                "description": "bob docs",
                "vector_backend": "faiss",
                "created_at": "2026-04-28T00:00:00+00:00",
                "updated_at": "2026-04-28T00:00:00+00:00",
            },
        ]
    )

    collections = service.list_collections(owner_id="user-1")

    assert [item["id"] for item in collections] == ["collection-1"]


def test_get_collection_rejects_other_users_collection() -> None:
    service, repository = create_collection_service()
    repository.items.append(
        {
            "id": "collection-1",
            "owner_id": "user-2",
            "name": "bob-kb",
            "description": "bob docs",
            "vector_backend": "faiss",
            "created_at": "2026-04-28T00:00:00+00:00",
            "updated_at": "2026-04-28T00:00:00+00:00",
        }
    )

    with pytest.raises(NotFoundError) as exc_info:
        service.get_collection("collection-1", owner_id="user-1")

    assert exc_info.value.code == "COLLECTION_NOT_FOUND"


def test_collection_model_uses_owner_scoped_unique_constraint() -> None:
    owner_scoped_constraints = [
        constraint
        for constraint in CollectionModel.__table__.constraints
        if getattr(constraint, "name", None) == "uq_collections_owner_name"
    ]

    assert len(owner_scoped_constraints) == 1
    constraint = owner_scoped_constraints[0]
    assert tuple(column.name for column in constraint.columns) == ("owner_id", "name")


def test_ensure_collection_name_scope_replaces_legacy_global_unique(monkeypatch) -> None:
    executed_sql: list[str] = []

    class FakeConnection:
        def execute(self, statement) -> None:
            executed_sql.append(str(statement))

    class FakeBeginContext:
        def __enter__(self) -> FakeConnection:
            return FakeConnection()

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeInspector:
        def get_unique_constraints(self, table_name: str) -> list[dict]:
            assert table_name == "collections"
            return [{"name": "collections_name_key", "column_names": ["name"]}]

    fake_engine = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql"),
        begin=lambda: FakeBeginContext(),
    )

    monkeypatch.setattr("app.db.session.inspect", lambda _engine: FakeInspector())

    _ensure_collection_name_scope(fake_engine)

    assert any(
        'ALTER TABLE collections DROP CONSTRAINT IF EXISTS "collections_name_key"' in sql
        for sql in executed_sql
    )
    assert any(
        "ADD CONSTRAINT uq_collections_owner_name UNIQUE (owner_id, name)" in sql
        for sql in executed_sql
    )
