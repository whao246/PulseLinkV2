from fastapi.testclient import TestClient
import httpx

from app.infrastructure.db.models import User
from app.main import create_app


def test_test_login_returns_token_in_local():
    response = TestClient(create_app(database_url="sqlite:///:memory:")).post(
        "/api/auth/test-login",
        json={"user_id": "usr_route"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["access_token"]


def test_test_login_persists_user_when_database_is_configured():
    app = create_app(database_url="sqlite:///:memory:")

    response = TestClient(app).post(
        "/api/auth/test-login",
        json={"user_id": "usr_route_db"},
    )

    assert response.status_code == 200
    db_session = app.state.db_session_factory()
    try:
        user = db_session.query(User).filter_by(id="usr_route_db").one()
        assert user.email == "usr_route_db@local.pulselink"
    finally:
        db_session.close()


def test_test_login_is_disabled_in_production(monkeypatch):
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

    response = TestClient(app).post(
        "/api/auth/test-login",
        json={"user_id": "usr_route_db"},
    )

    assert response.status_code == 404


def test_wechat_login_exchanges_code_and_persists_user(monkeypatch):
    monkeypatch.setenv("WECHAT_APP_ID", "wx-app")
    monkeypatch.setenv("WECHAT_APP_SECRET", "wx-secret")
    captured = {}

    def fake_get(url, params, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["timeout"] = timeout
        return httpx.Response(
            200,
            json={"openid": "openid_abc", "session_key": "session_key"},
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    app = create_app(database_url="sqlite:///:memory:")

    response = TestClient(app).post(
        "/api/auth/wechat-login",
        json={"code": "js-code"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["access_token"]
    assert data["token_type"] == "bearer"
    assert data["user_id"] == "wechat:openid_abc"
    assert captured["url"] == "https://api.weixin.qq.com/sns/jscode2session"
    assert captured["params"] == {
        "appid": "wx-app",
        "secret": "wx-secret",
        "js_code": "js-code",
        "grant_type": "authorization_code",
    }
    assert captured["timeout"] == 10

    db_session = app.state.db_session_factory()
    try:
        user = db_session.query(User).filter_by(id="wechat:openid_abc").one()
        assert user.display_name == "wechat:openid_abc"
    finally:
        db_session.close()


def test_wechat_login_rejects_invalid_code(monkeypatch):
    monkeypatch.setenv("WECHAT_APP_ID", "wx-app")
    monkeypatch.setenv("WECHAT_APP_SECRET", "wx-secret")

    def fake_get(url, params, timeout):
        return httpx.Response(200, json={"errcode": 40029, "errmsg": "invalid code"})

    monkeypatch.setattr(httpx, "get", fake_get)
    app = create_app(database_url="sqlite:///:memory:")

    response = TestClient(app).post(
        "/api/auth/wechat-login",
        json={"code": "bad-code"},
    )

    assert response.status_code == 401
    assert response.json()["detail"]["error_code"] == "WECHAT_LOGIN_FAILED"
