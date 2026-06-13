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
