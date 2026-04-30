from fastapi.testclient import TestClient

from app.api.deps import get_collection_service, get_current_user
from app.main import create_app


def test_health_check() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "app_name" in payload


def test_health_check_echoes_request_id_header() -> None:
    client = TestClient(create_app())
    response = client.get("/api/v1/health", headers={"X-Request-ID": "req-health-1"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-health-1"


def test_metrics_endpoint_exposes_prometheus_metrics() -> None:
    client = TestClient(create_app())
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "chatrobot_http_requests_total" in response.text
    assert "chatrobot_http_request_latency_seconds" in response.text


def test_authenticated_collection_list() -> None:
    app = create_app()

    class FakeCollectionService:
        def list_collections(self, owner_id: str) -> list[dict]:
            assert owner_id == "user-1"
            return [
                {
                    "id": "default-id",
                    "owner_id": "user-1",
                    "name": "default",
                    "description": "Default collection for tests.",
                    "vector_backend": "faiss",
                    "created_at": "2026-04-27T00:00:00+00:00",
                    "updated_at": "2026-04-27T00:00:00+00:00",
                }
            ]

    app.dependency_overrides[get_collection_service] = lambda: FakeCollectionService()
    app.dependency_overrides[get_current_user] = lambda: {"id": "user-1", "username": "alice"}
    client = TestClient(app)
    response = client.get("/api/v1/collections")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert any(item["name"] == "default" for item in payload)
