from fastapi.testclient import TestClient

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
