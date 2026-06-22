from fastapi.testclient import TestClient

from app.infrastructure.db.models import File
from app.main import create_app


def test_register_file_persists_to_database():
    app = create_app(database_url="sqlite:///:memory:")
    client = TestClient(app)

    response = client.post(
        "/api/files",
        headers={
            "Authorization": "Bearer test-token",
            "Idempotency-Key": "file-route-1",
        },
        json={
            "filename": "sample.pdf",
            "content_type": "application/pdf",
            "size_bytes": 1024,
            "storage_uri": "local://sample.pdf",
        },
    )

    assert response.status_code == 200
    file_id = response.json()["data"]["file"]["id"]

    db_session = app.state.db_session_factory()
    try:
        stored = db_session.query(File).filter_by(id=file_id).one()
        assert stored.filename == "sample.pdf"
        assert stored.user_id == "local-test-user"
        assert stored.storage_uri == "local://sample.pdf"
    finally:
        db_session.close()


def test_register_file_returns_existing_file_for_same_payload():
    app = create_app(database_url="sqlite:///:memory:")
    client = TestClient(app)
    payload = {
        "filename": "sample.pdf",
        "content_type": "application/pdf",
        "size_bytes": 1024,
        "storage_uri": "local://sample.pdf",
    }

    first = client.post(
        "/api/files",
        headers={"Idempotency-Key": "file-route-1"},
        json=payload,
    )
    second = client.post(
        "/api/files",
        headers={"Idempotency-Key": "file-route-2"},
        json=payload,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"]["file"]["id"] == second.json()["data"]["file"]["id"]


def test_create_pdf_upload_presign_returns_put_contract(monkeypatch):
    monkeypatch.setenv("COS_ENDPOINT", "http://minio:9000")
    monkeypatch.setenv("COS_BUCKET", "pulselink-local")
    app = create_app(database_url="sqlite:///:memory:")
    client = TestClient(app)

    response = client.post(
        "/api/uploads/pdf/presign",
        json={
            "file_name": "sample.pdf",
            "file_size": 1024,
            "sha256": "a" * 64,
            "content_type": "application/pdf",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["upload"]["method"] == "PUT"
    assert data["upload"]["url"].startswith("http://minio:9000/pulselink-local/uploads/")
    assert data["upload"]["headers"] == {"Content-Type": "application/pdf"}
    assert data["upload"]["expires_in"] == 900
    assert data["object"]["bucket"] == "pulselink-local"
    assert data["object"]["key"].endswith(".pdf")
    assert data["object"]["content_type"] == "application/pdf"
    assert data["storage_uri"] == f"cos://pulselink-local/{data['object']['key']}"


def test_create_pdf_upload_presign_rejects_non_pdf():
    app = create_app(database_url="sqlite:///:memory:")
    client = TestClient(app)

    response = client.post(
        "/api/uploads/pdf/presign",
        json={
            "file_name": "sample.txt",
            "file_size": 1024,
            "sha256": "a" * 64,
            "content_type": "text/plain",
        },
    )

    assert response.status_code == 422
