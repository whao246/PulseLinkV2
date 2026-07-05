import importlib
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.analysis.pipeline import PIPELINE_STEP_NAMES
from app.domain.scoring.dimensions import SCORING_DIMENSIONS
from app.domain.tasks.state_machine import StepStatus, TaskStatus
from app.infrastructure.db.base import Base
from app.infrastructure.db.models import (
    AnalysisTask,
    DocumentPage,
    EvidenceUnit,
    File,
    JudgmentCard,
    PageArtifact,
    Report,
    ScoreResult,
    TaskStep,
    User,
)
from app.infrastructure.queue.publisher import ANALYZE_DOCUMENT_JOB_PATH
from app.workers.jobs.analyze_document import DatabaseAnalysisOrchestrator, run


def test_analyze_document_job_invokes_orchestrator(monkeypatch):
    captured = {}

    class FakeOrchestrator:
        def run(self, *, task_id):
            captured["task_id"] = task_id

    monkeypatch.setattr(
        "app.workers.jobs.analyze_document.build_orchestrator",
        lambda: FakeOrchestrator(),
    )

    run(task_id="task_1")

    assert captured["task_id"] == "task_1"


def test_analyze_document_queue_path_is_importable():
    module_name, function_name = ANALYZE_DOCUMENT_JOB_PATH.rsplit(".", 1)

    target = getattr(importlib.import_module(module_name), function_name)

    assert target is run


def test_analyze_document_job_completes_task_and_writes_report(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'worker.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n/Type /Page\n/Type /Page\n%%EOF")

    session = SessionLocal()
    try:
        session.add(
            User(
                id="usr_worker",
                email="usr_worker@example.com",
                display_name="Worker User",
                is_active=True,
            )
        )
        session.add(
            File(
                id="file_worker",
                user_id="usr_worker",
                sha256="sha_worker",
                filename="sample.pdf",
                content_type="application/pdf",
                storage_uri=f"local://{pdf_path}",
            )
        )
        session.add(
            AnalysisTask(
                id="task_worker",
                user_id="usr_worker",
                file_id="file_worker",
                idempotency_key="idem_worker",
                task_type="bp_analysis",
                model_profile="default",
                status=TaskStatus.QUEUED.value,
            )
        )
        for step_name in PIPELINE_STEP_NAMES:
            session.add(
                TaskStep(
                    id=f"step_{step_name}",
                    task_id="task_worker",
                    step_name=step_name,
                    status=StepStatus.PENDING.value,
                    attempt_count=0,
                    max_attempts=3,
                )
            )
        session.commit()
    finally:
        session.close()

    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ARTIFACT_DIR", str(tmp_path / "artifacts"))

    run(task_id="task_worker")

    session = SessionLocal()
    try:
        task = session.query(AnalysisTask).filter_by(id="task_worker").one()
        steps = session.query(TaskStep).filter_by(task_id="task_worker").all()
        report = session.query(Report).filter_by(task_id="task_worker").one()
        score = session.query(ScoreResult).filter_by(task_id="task_worker").one()
        pages = session.query(DocumentPage).filter_by(task_id="task_worker").all()
        artifacts = session.query(PageArtifact).filter_by(task_id="task_worker").all()
        evidence = session.query(EvidenceUnit).filter_by(task_id="task_worker").all()
        judgment_cards = (
            session.query(JudgmentCard).filter_by(task_id="task_worker").all()
        )

        assert task.status == TaskStatus.COMPLETED.value
        assert {step.status for step in steps} == {StepStatus.SUCCEEDED.value}
        assert [step.step_name for step in sorted(steps, key=lambda step: step.payload["order"])] == list(
            PIPELINE_STEP_NAMES
        )
        assert all(step.payload["completed"] is True for step in steps)
        assert len(pages) == 2
        assert all("placeholder" not in (page.text or "") for page in pages)
        assert {page.metadata_json["text_status"] for page in pages} <= {
            "extracted",
            "parser_unavailable",
        }
        assert len(artifacts) >= 1
        assert len(evidence) >= 1
        assert report.status == "ready"
        assert report.payload["parse_summary"]["page_count"] == 2
        assert score.total_score > 0
        dimensions = score.score_payload["dimensions"]
        assert len(dimensions) == 8
        assert len(judgment_cards) == 8
        assert score.total_score == sum(dimension["score"] for dimension in dimensions)
        assert report.payload["score_result"]["dimensions"] == dimensions
        for dimension in dimensions:
            assert dimension["key"]
            assert dimension["name"]
            assert dimension["score"] >= 0
            assert dimension["max_score"] > 0
            assert dimension["reason"]
            assert dimension["suggestions_for_bp"]
            assert dimension["due_diligence_questions"]
            assert "evidence_refs" in dimension
    finally:
        session.close()


def test_analyze_document_job_uses_model_gateway_for_scoring(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'worker-llm.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n/Type /Page\n%%EOF")

    session = SessionLocal()
    try:
        session.add(
            User(
                id="usr_worker",
                email="usr_worker@example.com",
                display_name="Worker User",
                is_active=True,
            )
        )
        session.add(
            File(
                id="file_worker",
                user_id="usr_worker",
                sha256="sha_worker",
                filename="sample.pdf",
                content_type="application/pdf",
                storage_uri=f"local://{pdf_path}",
            )
        )
        session.add(
            AnalysisTask(
                id="task_worker_llm",
                user_id="usr_worker",
                file_id="file_worker",
                idempotency_key="idem_worker_llm",
                task_type="bp_analysis",
                model_profile="MiniMax-M3",
                status=TaskStatus.QUEUED.value,
            )
        )
        for step_name in PIPELINE_STEP_NAMES:
            session.add(
                TaskStep(
                    id=f"llm_step_{step_name}",
                    task_id="task_worker_llm",
                    step_name=step_name,
                    status=StepStatus.PENDING.value,
                    attempt_count=0,
                    max_attempts=3,
                )
            )
        session.commit()
    finally:
        session.close()

    class FakeModelGateway:
        def __init__(self):
            self.calls = []

        def complete_json(self, *, messages, temperature=0):
            self.calls.append({"messages": messages, "temperature": temperature})
            return {
                "dimensions": [
                    {
                        "key": dimension.key,
                        "score": dimension.max_score,
                        "reason": f"LLM reason for {dimension.key}",
                        "evidence_refs": [f"offline:{dimension.key}"],
                        "suggestions_for_bp": [f"补充 {dimension.name}"],
                        "due_diligence_questions": [f"核验 {dimension.name}"],
                    }
                    for dimension in SCORING_DIMENSIONS
                ]
            }

        def understand_image_json(self, *, prompt, image_bytes):
            return {"fallback": True}

    fake_model = FakeModelGateway()
    orchestrator = DatabaseAnalysisOrchestrator(
        session_factory=sessionmaker(bind=engine, expire_on_commit=False),
        artifact_dir=tmp_path / "artifacts",
        model_gateway=fake_model,
    )

    orchestrator.run(task_id="task_worker_llm")

    session = SessionLocal()
    try:
        score = session.query(ScoreResult).filter_by(task_id="task_worker_llm").one()
        report = session.query(Report).filter_by(task_id="task_worker_llm").one()
        cards = session.query(JudgmentCard).filter_by(task_id="task_worker_llm").all()

        assert len(fake_model.calls) == 1
        assert fake_model.calls[0]["temperature"] == 0
        assert "问题与需求强度" in fake_model.calls[0]["messages"][1]["content"]
        assert score.total_score == 100
        assert score.score_payload["score_source"] == "llm"
        assert score.score_payload["dimensions"][0]["reason"].startswith("LLM reason")
        assert report.payload["score_result"]["score_source"] == "llm"
        assert report.payload["score_result"]["dimensions"] == score.score_payload["dimensions"]
        assert len(cards) == 8
        assert {card.verdict for card in cards} == {"strong"}
    finally:
        session.close()

def test_analyze_document_job_marks_retrying_when_step_can_retry(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'worker-failed.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    session = SessionLocal()
    try:
        session.add(
            User(
                id="usr_worker",
                email="usr_worker@example.com",
                display_name="Worker User",
                is_active=True,
            )
        )
        session.add(
            File(
                id="file_worker",
                user_id="usr_worker",
                sha256="sha_worker",
                filename="sample.pdf",
                content_type="application/pdf",
                storage_uri="cos://bucket/sample.pdf",
            )
        )
        session.add(
            AnalysisTask(
                id="task_worker_failed",
                user_id="usr_worker",
                file_id="file_worker",
                idempotency_key="idem_worker_failed",
                task_type="bp_analysis",
                model_profile="default",
                status=TaskStatus.QUEUED.value,
            )
        )
        for step_name in PIPELINE_STEP_NAMES:
            session.add(
                TaskStep(
                    id=f"failed_step_{step_name}",
                    task_id="task_worker_failed",
                    step_name=step_name,
                    status=StepStatus.PENDING.value,
                    attempt_count=0,
                    max_attempts=3,
                )
            )
        session.commit()
    finally:
        session.close()

    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ARTIFACT_DIR", str(tmp_path / "artifacts"))

    try:
        run(task_id="task_worker_failed")
    except ValueError:
        pass

    session = SessionLocal()
    try:
        task = session.query(AnalysisTask).filter_by(id="task_worker_failed").one()
        load_step = (
            session.query(TaskStep)
            .filter_by(task_id="task_worker_failed", step_name="load_document")
            .one()
        )

        assert task.status == TaskStatus.QUEUED.value
        assert "unsupported storage_uri" in task.error_message
        assert load_step.status == StepStatus.RETRYING.value
        assert load_step.attempt_count == 1
        assert "unsupported storage_uri" in load_step.error_message
    finally:
        session.close()


def test_analyze_document_job_marks_failed_when_step_retries_exhausted(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'worker-exhausted.db'}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    session = SessionLocal()
    try:
        session.add(
            User(
                id="usr_worker",
                email="usr_worker@example.com",
                display_name="Worker User",
                is_active=True,
            )
        )
        session.add(
            File(
                id="file_worker",
                user_id="usr_worker",
                sha256="sha_worker",
                filename="sample.pdf",
                content_type="application/pdf",
                storage_uri="cos://bucket/sample.pdf",
            )
        )
        session.add(
            AnalysisTask(
                id="task_worker_exhausted",
                user_id="usr_worker",
                file_id="file_worker",
                idempotency_key="idem_worker_exhausted",
                task_type="bp_analysis",
                model_profile="default",
                status=TaskStatus.QUEUED.value,
            )
        )
        for step_name in PIPELINE_STEP_NAMES:
            session.add(
                TaskStep(
                    id=f"exhausted_step_{step_name}",
                    task_id="task_worker_exhausted",
                    step_name=step_name,
                    status=StepStatus.PENDING.value,
                    attempt_count=0,
                    max_attempts=1,
                )
            )
        session.commit()
    finally:
        session.close()

    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ARTIFACT_DIR", str(tmp_path / "artifacts"))

    try:
        run(task_id="task_worker_exhausted")
    except ValueError:
        pass

    session = SessionLocal()
    try:
        task = session.query(AnalysisTask).filter_by(id="task_worker_exhausted").one()
        load_step = (
            session.query(TaskStep)
            .filter_by(task_id="task_worker_exhausted", step_name="load_document")
            .one()
        )

        assert task.status == TaskStatus.FAILED.value
        assert "unsupported storage_uri" in task.error_message
        assert load_step.status == StepStatus.FAILED.value
        assert load_step.attempt_count == 1
        assert "unsupported storage_uri" in load_step.error_message
    finally:
        session.close()
