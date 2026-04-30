from fastapi.testclient import TestClient

from app.api.deps import get_collection_service, get_current_user, get_user_service
from app.main import create_app


class FakeUserService:
    def register(self, payload):
        return {
            "id": "user-1",
            "username": payload.username,
            "email": payload.email,
            "hashed_password": "hidden",
            "is_active": True,
            "created_at": "2026-04-28T00:00:00+00:00",
            "updated_at": "2026-04-28T00:00:00+00:00",
        }

    def authenticate(self, *, identifier: str, password: str):
        assert identifier == "alice"
        assert password == "secret123"
        return {
            "id": "user-1",
            "username": "alice",
            "email": "alice@example.com",
            "hashed_password": "hidden",
            "is_active": True,
            "created_at": "2026-04-28T00:00:00+00:00",
            "updated_at": "2026-04-28T00:00:00+00:00",
        }

    def get_user(self, user_id: str):
        return {
            "id": user_id,
            "username": "alice",
            "email": "alice@example.com",
            "hashed_password": "hidden",
            "is_active": True,
            "created_at": "2026-04-28T00:00:00+00:00",
            "updated_at": "2026-04-28T00:00:00+00:00",
        }


def test_register_returns_token() -> None:
    app = create_app()
    app.dependency_overrides[get_user_service] = lambda: FakeUserService()
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "alice",
            "email": "alice@example.com",
            "password": "secret123",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["access_token"]
    assert payload["user"]["username"] == "alice"


def test_login_returns_token() -> None:
    app = create_app()
    app.dependency_overrides[get_user_service] = lambda: FakeUserService()
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/login",
        data={
            "username": "alice",
            "password": "secret123",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["user"]["email"] == "alice@example.com"


def test_me_returns_current_user() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "user-1",
        "username": "alice",
        "email": "alice@example.com",
        "hashed_password": "hidden",
        "is_active": True,
        "created_at": "2026-04-28T00:00:00+00:00",
        "updated_at": "2026-04-28T00:00:00+00:00",
    }
    client = TestClient(app)

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    payload = response.json()
    assert payload["username"] == "alice"
    assert payload["email"] == "alice@example.com"


def test_protected_route_requires_auth() -> None:
    app = create_app()

    class FakeCollectionService:
        def list_collections(self, owner_id: str) -> list[dict]:
            return []

    app.dependency_overrides[get_collection_service] = lambda: FakeCollectionService()
    client = TestClient(app)
    response = client.get("/api/v1/collections")
    assert response.status_code == 401


def test_protected_route_with_auth_override() -> None:
    app = create_app()

    class FakeCollectionService:
        def list_collections(self, owner_id: str) -> list[dict]:
            assert owner_id == "user-1"
            return [
                {
                    "id": "collection-1",
                    "owner_id": "user-1",
                    "name": "我的知识库",
                    "description": "测试数据",
                    "vector_backend": "faiss",
                    "created_at": "2026-04-28T00:00:00+00:00",
                    "updated_at": "2026-04-28T00:00:00+00:00",
                }
            ]

    app.dependency_overrides[get_current_user] = lambda: {"id": "user-1", "username": "alice"}
    app.dependency_overrides[get_collection_service] = lambda: FakeCollectionService()
    client = TestClient(app)

    response = client.get("/api/v1/collections")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["name"] == "我的知识库"
