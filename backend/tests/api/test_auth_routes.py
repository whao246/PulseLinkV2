from fastapi.testclient import TestClient

from app.main import create_app


def test_test_login_returns_token_in_local():
    response = TestClient(create_app(database_url="sqlite:///:memory:")).post(
        "/api/auth/test-login",
        json={"user_id": "usr_route"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["access_token"]
