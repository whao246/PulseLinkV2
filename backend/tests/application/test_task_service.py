import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import app.infrastructure.db.models  # noqa: F401
from app.application.task_service import TaskService
from app.infrastructure.db.base import Base
from app.infrastructure.db.models import AnalysisTask, File, TaskStep, User


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    session.add(
        User(
            id="usr_1",
            email="usr_1@example.com",
            display_name="User One",
            is_active=True,
        )
    )
    session.commit()
    session.add(
        File(
            id="file_1",
            user_id="usr_1",
            sha256="sha256_file_1",
            filename="file_1.pdf",
            content_type="application/pdf",
            size_bytes=123,
            storage_uri="s3://bucket/file_1.pdf",
        )
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()


class QueuePublisherSpy:
    def __init__(self):
        self.published_task_ids = []

    def publish_analyze_document(self, *, task_id):
        self.published_task_ids.append(task_id)


class FailsOnceQueuePublisherSpy:
    def __init__(self):
        self.published_task_ids = []
        self.calls = 0

    def publish_analyze_document(self, *, task_id):
        self.calls += 1
        self.published_task_ids.append(task_id)
        if self.calls == 1:
            raise RuntimeError("queue unavailable")


def test_task_service_returns_same_task_for_same_idempotency_key(db_session):
    service = TaskService(db_session=db_session, queue_publisher=None)
    user_id = "usr_1"
    file_id = "file_1"

    first = service.create_task(
        user_id=user_id, file_id=file_id, idempotency_key="idem_1", options={}
    )
    second = service.create_task(
        user_id=user_id, file_id=file_id, idempotency_key="idem_1", options={}
    )

    assert first.id == second.id
    assert second.payload["queue_publish_status"] == "pending"


def test_task_service_initializes_pipeline_steps(db_session):
    service = TaskService(db_session=db_session, queue_publisher=None)

    task = service.create_task(
        user_id="usr_1", file_id="file_1", idempotency_key="idem_2", options={}
    )
    steps = service.list_steps(task.id)

    assert task.status == "queued"
    assert [step.step_name for step in steps] == [
        "load_document",
        "parse_text_layout",
        "detect_tables_and_figures",
        "render_candidate_pages",
        "vision_understanding",
        "build_evidence_units",
        "score_and_judge",
        "assemble_report",
    ]
    assert [step.status for step in steps] == ["pending"] * 8


def test_task_service_does_not_republish_for_same_idempotency_key(db_session):
    queue_publisher = QueuePublisherSpy()
    service = TaskService(db_session=db_session, queue_publisher=queue_publisher)

    first = service.create_task(
        user_id="usr_1", file_id="file_1", idempotency_key="idem_3", options={}
    )
    second = service.create_task(
        user_id="usr_1", file_id="file_1", idempotency_key="idem_3", options={}
    )

    assert first.id == second.id
    assert queue_publisher.published_task_ids == [first.id]


def test_task_service_publishes_new_task_once(db_session):
    queue_publisher = QueuePublisherSpy()
    service = TaskService(db_session=db_session, queue_publisher=queue_publisher)

    task = service.create_task(
        user_id="usr_1", file_id="file_1", idempotency_key="idem_4", options={}
    )

    assert queue_publisher.published_task_ids == [task.id]


def test_task_service_uses_saved_task_id_after_publish_claim(db_session, monkeypatch):
    queue_publisher = QueuePublisherSpy()
    service = TaskService(db_session=db_session, queue_publisher=queue_publisher)
    original_claim = service.tasks.claim_queue_publish

    def claim_and_detach(task_id):
        claimed = original_claim(task_id)
        task = next(
            model
            for model in db_session.identity_map.values()
            if isinstance(model, AnalysisTask)
        )
        db_session.expunge(task)
        return claimed

    monkeypatch.setattr(service.tasks, "claim_queue_publish", claim_and_detach)

    service.create_task(
        user_id="usr_1",
        file_id="file_1",
        idempotency_key="idem_saved_task_id",
        options={},
    )

    task_id = (
        db_session.query(AnalysisTask)
        .filter_by(idempotency_key="idem_saved_task_id")
        .one()
        .id
    )
    assert queue_publisher.published_task_ids == [task_id]


def test_task_service_persists_model_profile_option(db_session):
    service = TaskService(db_session=db_session, queue_publisher=None)

    task = service.create_task(
        user_id="usr_1",
        file_id="file_1",
        idempotency_key="idem_5",
        options={"model_profile": "MiniMax-M3"},
    )

    assert task.model_profile == "MiniMax-M3"


def test_task_service_retries_publish_for_existing_unpublished_task(db_session):
    queue_publisher = FailsOnceQueuePublisherSpy()
    service = TaskService(db_session=db_session, queue_publisher=queue_publisher)

    with pytest.raises(RuntimeError, match="queue unavailable"):
        service.create_task(
            user_id="usr_1",
            file_id="file_1",
            idempotency_key="idem_publish_retry",
            options={},
        )

    task_after_failure = (
        db_session.query(AnalysisTask)
        .filter_by(user_id="usr_1", idempotency_key="idem_publish_retry")
        .one()
    )
    assert task_after_failure.payload["queue_publish_status"] == "pending"

    retried = service.create_task(
        user_id="usr_1",
        file_id="file_1",
        idempotency_key="idem_publish_retry",
        options={},
    )

    assert retried.id == task_after_failure.id
    assert db_session.query(AnalysisTask).count() == 1
    assert db_session.query(TaskStep).count() == 8
    assert queue_publisher.calls == 2
    assert queue_publisher.published_task_ids == [retried.id, retried.id]
    assert retried.payload["queue_publish_status"] == "published"


def test_task_service_does_not_publish_when_existing_task_is_already_claimed(db_session):
    existing_service = TaskService(db_session=db_session, queue_publisher=None)
    existing = existing_service.create_task(
        user_id="usr_1",
        file_id="file_1",
        idempotency_key="idem_publish_claimed",
        options={},
    )
    existing.payload = {"queue_publish_status": "publishing"}
    db_session.add(existing)
    db_session.commit()

    queue_publisher = QueuePublisherSpy()
    service = TaskService(db_session=db_session, queue_publisher=queue_publisher)

    retried = service.create_task(
        user_id="usr_1",
        file_id="file_1",
        idempotency_key="idem_publish_claimed",
        options={},
    )

    assert retried.id == existing.id
    assert queue_publisher.published_task_ids == []
    assert retried.payload["queue_publish_status"] == "publishing"


def test_task_service_does_not_republish_when_existing_task_is_published(db_session):
    existing_service = TaskService(db_session=db_session, queue_publisher=None)
    existing = existing_service.create_task(
        user_id="usr_1",
        file_id="file_1",
        idempotency_key="idem_publish_done",
        options={},
    )
    existing.payload = {"queue_publish_status": "published"}
    db_session.add(existing)
    db_session.commit()

    queue_publisher = QueuePublisherSpy()
    service = TaskService(db_session=db_session, queue_publisher=queue_publisher)

    retried = service.create_task(
        user_id="usr_1",
        file_id="file_1",
        idempotency_key="idem_publish_done",
        options={},
    )

    assert retried.id == existing.id
    assert queue_publisher.published_task_ids == []
    assert retried.payload["queue_publish_status"] == "published"


def test_task_service_does_not_republish_legacy_published_task(db_session):
    existing_service = TaskService(db_session=db_session, queue_publisher=None)
    existing = existing_service.create_task(
        user_id="usr_1",
        file_id="file_1",
        idempotency_key="idem_legacy_publish_done",
        options={},
    )
    existing.payload = {"queue_published": True}
    db_session.add(existing)
    db_session.commit()

    queue_publisher = QueuePublisherSpy()
    service = TaskService(db_session=db_session, queue_publisher=queue_publisher)

    retried = service.create_task(
        user_id="usr_1",
        file_id="file_1",
        idempotency_key="idem_legacy_publish_done",
        options={},
    )

    assert retried.id == existing.id
    assert queue_publisher.published_task_ids == []
    assert retried.payload == {"queue_published": True}


def test_task_service_recovers_from_idempotency_integrity_error(db_session, monkeypatch):
    existing_service = TaskService(db_session=db_session, queue_publisher=None)
    existing = existing_service.create_task(
        user_id="usr_1",
        file_id="file_1",
        idempotency_key="idem_integrity",
        options={},
    )
    existing_id = existing.id
    db_session.expunge_all()

    queue_publisher = QueuePublisherSpy()
    service = TaskService(db_session=db_session, queue_publisher=queue_publisher)
    original_get = service.tasks.get_by_idempotency_key
    get_calls = 0

    def fake_get_by_idempotency_key(user_id, idempotency_key):
        nonlocal get_calls
        get_calls += 1
        if get_calls == 1:
            return None
        return original_get(user_id, idempotency_key)

    original_commit = db_session.commit
    commit_calls = 0

    def fake_commit():
        nonlocal commit_calls
        commit_calls += 1
        if commit_calls == 1:
            raise IntegrityError("insert", {}, Exception("unique constraint"))
        return original_commit()

    monkeypatch.setattr(service.tasks, "get_by_idempotency_key", fake_get_by_idempotency_key)
    monkeypatch.setattr(db_session, "commit", fake_commit)

    recovered = service.create_task(
        user_id="usr_1",
        file_id="file_1",
        idempotency_key="idem_integrity",
        options={},
    )

    assert recovered.id == existing_id
    assert db_session.query(AnalysisTask).count() == 1
    assert db_session.query(TaskStep).count() == 8
    assert queue_publisher.published_task_ids == []


def test_task_service_list_steps_orders_unknown_steps_stably(db_session):
    service = TaskService(db_session=db_session, queue_publisher=None)
    task = service.create_task(
        user_id="usr_1",
        file_id="file_1",
        idempotency_key="idem_steps_order",
        options={},
    )
    db_session.add_all(
        [
            TaskStep(
                id="unknown_b",
                task_id=task.id,
                step_name="zzz_unknown_b",
                status="pending",
            ),
            TaskStep(
                id="unknown_a",
                task_id=task.id,
                step_name="zzz_unknown_a",
                status="pending",
            ),
            TaskStep(
                id="unknown_c",
                task_id=task.id,
                step_name="aaa_unknown",
                status="pending",
            ),
        ]
    )
    db_session.commit()

    steps = service.list_steps(task.id)

    assert [(step.step_name, step.id) for step in steps[-3:]] == [
        ("aaa_unknown", "unknown_c"),
        ("zzz_unknown_a", "unknown_a"),
        ("zzz_unknown_b", "unknown_b"),
    ]
