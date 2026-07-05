import pytest

from fastapi.testclient import TestClient

from app.main import create_app


def test_create_app_registers_health_route():
    app = create_app(database_url="sqlite:///:memory:", run_analysis_inline=True)
    response = TestClient(app).get("/api/health")
    body = response.json()

    assert response.status_code == 200
    assert body["code"] == 0
    assert body["message"] == "ok"
    assert body["data"]["status"] == "ok"
    assert body["data"]["version"] == "0.1.0"
    assert body["request_id"]


def test_health_route_returns_request_id_from_header():
    app = create_app(database_url="sqlite:///:memory:", run_analysis_inline=True)
    response = TestClient(app).get("/api/health", headers={"X-Request-Id": "req_test"})

    assert response.status_code == 200
    assert response.json()["request_id"] == "req_test"


def test_prod_app_rejects_unsafe_default_config(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("JWT_SECRET", "change-me")

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        create_app(database_url="mysql+pymysql://u:p@db:3306/pulselink")


def test_prod_app_accepts_required_config(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("WECHAT_APP_ID", "wx-app")
    monkeypatch.setenv("WECHAT_APP_SECRET", "wx-secret")
    monkeypatch.setenv("COS_BUCKET", "pulselink-prod")
    monkeypatch.setenv("COS_ENDPOINT", "https://pulselink-prod.cos.ap-guangzhou.myqcloud.com")
    monkeypatch.setenv("COS_SECRET_ID", "cos-id")
    monkeypatch.setenv("COS_SECRET_KEY", "cos-key")
    monkeypatch.setenv("LLM_API_BASE", "https://api.minimax.chat/v1")
    monkeypatch.setenv("LLM_API_KEY", "llm-key")
    monkeypatch.setenv("LLM_MODEL", "MiniMax-M3")

    app = create_app(database_url="mysql+pymysql://u:p@db:3306/pulselink")

    assert app.state.database_url == "mysql+pymysql://u:p@db:3306/pulselink"
