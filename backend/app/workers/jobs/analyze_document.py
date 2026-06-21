from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.tasks.state_machine import StepStatus, TaskStatus
from app.infrastructure.db.models import AnalysisTask, File, Report, ScoreResult, TaskStep
from app.pipeline.offline import analyze_pdf_offline


def build_orchestrator():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required to run analyze_document job")
    artifact_dir = Path(os.getenv("ARTIFACT_DIR", "/tmp/pulselink-artifacts"))
    engine = create_engine(database_url)
    return DatabaseAnalysisOrchestrator(
        session_factory=sessionmaker(bind=engine, expire_on_commit=False),
        artifact_dir=artifact_dir,
    )


def run(*, task_id: str) -> None:
    orchestrator = build_orchestrator()
    orchestrator.run(task_id=task_id)


class DatabaseAnalysisOrchestrator:
    def __init__(self, *, session_factory, artifact_dir: Path):
        self.session_factory = session_factory
        self.artifact_dir = artifact_dir

    def run(self, *, task_id: str) -> None:
        db_session = self.session_factory()
        try:
            task = db_session.query(AnalysisTask).filter_by(id=task_id).one()
            if task.status == TaskStatus.COMPLETED.value:
                return

            task.status = TaskStatus.RUNNING.value
            db_session.add(task)
            db_session.commit()

            try:
                file = db_session.query(File).filter_by(id=task.file_id).one()
                pdf_path = _local_pdf_path(file.storage_uri)
                result = analyze_pdf_offline(pdf_path, artifact_dir=self.artifact_dir)
                self._mark_steps_succeeded(db_session, task_id=task_id)
                self._write_score(db_session, task_id=task_id, result=result)
                self._write_report(
                    db_session,
                    task_id=task_id,
                    file=file,
                    result=result,
                )
                task.status = TaskStatus.COMPLETED.value
                task.error_message = None
                db_session.add(task)
                db_session.commit()
            except Exception as exc:
                db_session.rollback()
                task = db_session.query(AnalysisTask).filter_by(id=task_id).one()
                task.status = TaskStatus.FAILED.value
                task.error_message = str(exc)
                db_session.add(task)
                db_session.commit()
                raise
        finally:
            db_session.close()

    def _mark_steps_succeeded(self, db_session, *, task_id: str) -> None:
        steps = db_session.query(TaskStep).filter_by(task_id=task_id).all()
        for step in steps:
            step.status = StepStatus.SUCCEEDED.value
            db_session.add(step)

    def _write_score(self, db_session, *, task_id: str, result) -> None:
        score = db_session.query(ScoreResult).filter_by(task_id=task_id).one_or_none()
        if score is None:
            score = ScoreResult(id=f"score_{task_id}", task_id=task_id)
        score.total_score = result.score_result.potential_score
        score.score_payload = {
            "potential_score": result.score_result.potential_score,
            "parse_summary": _parse_summary_payload(result),
        }
        db_session.add(score)

    def _write_report(self, db_session, *, task_id: str, file: File, result) -> None:
        report = db_session.query(Report).filter_by(task_id=task_id).one_or_none()
        if report is None:
            report = Report(id=f"report_{task_id}", task_id=task_id)
        report.title = f"{file.filename} 分析报告"
        report.status = "ready"
        report.storage_uri = None
        report.payload = {
            "file": {
                "id": file.id,
                "filename": file.filename,
                "storage_uri": file.storage_uri,
            },
            "parse_summary": _parse_summary_payload(result),
            "score_result": {
                "potential_score": result.score_result.potential_score,
            },
        }
        db_session.add(report)


def _local_pdf_path(storage_uri: str) -> Path:
    if storage_uri.startswith("local://"):
        path = storage_uri.removeprefix("local://")
        return Path(path)
    raise ValueError(f"unsupported storage_uri for worker: {storage_uri}")


def _parse_summary_payload(result) -> dict:
    summary = result.parse_summary
    return {
        "page_count": summary.page_count,
        "block_count": summary.block_count,
        "table_count": summary.table_count,
        "evidence_unit_count": summary.evidence_unit_count,
    }
