from fastapi.testclient import TestClient

from app.main import create_app


def test_root_page_serves_frontend() -> None:
    client = TestClient(create_app())
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "ChatRobot_v3 RAG 工作台" in response.text
    assert "登录账号" in response.text


def test_register_page_serves_frontend() -> None:
    client = TestClient(create_app())
    response = client.get("/register")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "注册账号" in response.text
