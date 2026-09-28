from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_register_and_login():
    # 注册
    resp = client.post("/api/v1/auth/register", json={
        "username": "pytest_user",
        "password": "pytest_pass",
    })
    assert resp.status_code in (201, 400)  # 400 表示已存在（多次运行时）

    # 登录
    resp = client.post("/api/v1/auth/login", json={
        "username": "pytest_user",
        "password": "pytest_pass",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_protected_endpoint_without_token():
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401