import pytest
from fastapi.testclient import TestClient

from app.infrastructure.db.models import AnalysisTask, TaskStep
from app.main import create_app


@pytest.fixture
def authenticated_client():
    client = TestClient(create_app(database_url="sqlite:///:memory:"))
    client.headers.update({"Authorization": "Bearer test-token"})
    return client


def test_create_task_requires_idempotency_key(authenticated_client):
    response = authenticated_client.post(
        "/api/analysis-tasks",
        json={"file_id": "file_1", "options": {}},
    )

    assert response.status_code == 400
    assert response.json()["data"]["error_code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_create_task_uses_task_service_when_available():
    captured = {}

    class CreatedTask:
        id = "task_route"
        status = "queued"

    class FakeTaskService:
        def create_task(self, *, user_id, file_id, idempotency_key, options):
            captured["user_id"] = user_id
            captured["file_id"] = file_id
            captured["idempotency_key"] = idempotency_key
            captured["options"] = options
            return CreatedTask()

    app = create_app(database_url="sqlite:///:memory:")
    app.state.task_service = FakeTaskService()
    client = TestClient(app)

    response = client.post(
        "/api/analysis-tasks",
        headers={
            "Authorization": "Bearer test-token",
            "Idempotency-Key": "idem_route",
        },
        json={"file_id": "file_1", "options": {"model_profile": "MiniMax-M3"}},
    )

    assert response.status_code == 200
    assert response.json()["data"]["task_id"] == "task_route"
    assert captured == {
        "user_id": "local-test-user",
        "file_id": "file_1",
        "idempotency_key": "idem_route",
        "options": {"model_profile": "MiniMax-M3"},
    }


def test_create_task_persists_task_steps_and_publishes_queue():
    class QueuePublisherSpy:
        def __init__(self):
            self.published_task_ids = []

        def publish_analyze_document(self, *, task_id):
            self.published_task_ids.append(task_id)

    app = create_app(database_url="sqlite:///:memory:")
    app.state.queue_publisher = QueuePublisherSpy()
    client = TestClient(app)
    file_response = client.post(
        "/api/files",
        headers={"Idempotency-Key": "file-route-task"},
        json={
            "filename": "sample.pdf",
            "content_type": "application/pdf",
            "size_bytes": 1024,
            "storage_uri": "local://sample.pdf",
        },
    )
    file_id = file_response.json()["data"]["file"]["id"]

    response = client.post(
        "/api/analysis-tasks",
        headers={
            "Authorization": "Bearer test-token",
            "Idempotency-Key": "task-route-db",
        },
        json={"file_id": file_id, "options": {"model_profile": "MiniMax-M3"}},
    )

    assert response.status_code == 200
    task_id = response.json()["data"]["task"]["id"]
    assert app.state.queue_publisher.published_task_ids == [task_id]

    db_session = app.state.db_session_factory()
    try:
        task = db_session.query(AnalysisTask).filter_by(id=task_id).one()
        steps = db_session.query(TaskStep).filter_by(task_id=task_id).all()
        assert task.file_id == file_id
        assert task.model_profile == "MiniMax-M3"
        assert task.payload["queue_publish_status"] == "published"
        assert len(steps) == 8
    finally:
        db_session.close()
