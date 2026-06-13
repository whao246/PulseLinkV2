from fastapi.testclient import TestClient

from app.main import create_app


def test_create_app_registers_health_route():
    app = create_app(database_url="sqlite:///:memory:", run_analysis_inline=True)
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ok"
