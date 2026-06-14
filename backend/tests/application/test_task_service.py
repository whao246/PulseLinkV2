import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.infrastructure.db.models  # noqa: F401
from app.application.task_service import TaskService
from app.infrastructure.db.base import Base


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


class QueuePublisherSpy:
    def __init__(self):
        self.published_task_ids = []

    def publish_analyze_document(self, *, task_id):
        self.published_task_ids.append(task_id)


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


def test_task_service_initializes_pipeline_steps(db_session):
    service = TaskService(db_session=db_session, queue_publisher=None)

    task = service.create_task(
        user_id="usr_1", file_id="file_1", idempotency_key="idem_2", options={}
    )
    steps = service.list_steps(task.id)

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


def test_task_service_persists_model_profile_option(db_session):
    service = TaskService(db_session=db_session, queue_publisher=None)

    task = service.create_task(
        user_id="usr_1",
        file_id="file_1",
        idempotency_key="idem_5",
        options={"model_profile": "MiniMax-M3"},
    )

    assert task.model_profile == "MiniMax-M3"
