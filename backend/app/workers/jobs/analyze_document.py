from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.analysis.pipeline import PIPELINE_STEP_NAMES
from app.domain.tasks.state_machine import StepStatus, TaskStatus
from app.infrastructure.db.models import (
    AnalysisTask,
    DocumentPage,
    EvidenceUnit,
    File,
    PageArtifact,
    Report,
    ScoreResult,
    TaskStep,
)
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
                context = {"task": task}
                for order, step_name in enumerate(PIPELINE_STEP_NAMES):
                    self._run_step(
                        db_session,
                        task_id=task_id,
                        step_name=step_name,
                        order=order,
                        context=context,
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

    def _run_step(
        self,
        db_session,
        *,
        task_id: str,
        step_name: str,
        order: int,
        context: dict,
    ) -> None:
        step = (
            db_session.query(TaskStep)
            .filter_by(task_id=task_id, step_name=step_name)
            .one()
        )
        step.status = StepStatus.RUNNING.value
        step.error_message = None
        step.payload = {"order": order, "completed": False}
        db_session.add(step)
        db_session.commit()

        try:
            payload = getattr(self, f"_step_{step_name}")(db_session, context)
        except Exception as exc:
            db_session.rollback()
            step = (
                db_session.query(TaskStep)
                .filter_by(task_id=task_id, step_name=step_name)
                .one()
            )
            step.status = StepStatus.FAILED.value
            step.error_message = str(exc)
            step.payload = {"order": order, "completed": False}
            db_session.add(step)
            db_session.commit()
            raise

        step = (
            db_session.query(TaskStep)
            .filter_by(task_id=task_id, step_name=step_name)
            .one()
        )
        step.status = StepStatus.SUCCEEDED.value
        step.payload = {"order": order, "completed": True, **(payload or {})}
        db_session.add(step)
        db_session.commit()

    def _step_load_document(self, db_session, context: dict) -> dict:
        task = context["task"]
        file = db_session.query(File).filter_by(id=task.file_id).one()
        pdf_path = _local_pdf_path(file.storage_uri)
        context["file"] = file
        context["pdf_path"] = pdf_path
        return {
            "file_id": file.id,
            "filename": file.filename,
            "storage_uri": file.storage_uri,
        }

    def _step_parse_text_layout(self, db_session, context: dict) -> dict:
        task = context["task"]
        result = analyze_pdf_offline(context["pdf_path"], artifact_dir=self.artifact_dir)
        context["analysis_result"] = result
        page_count = result.parse_summary.page_count
        for page_number in range(1, page_count + 1):
            page = (
                db_session.query(DocumentPage)
                .filter_by(task_id=task.id, page_number=page_number)
                .one_or_none()
            )
            if page is None:
                page = DocumentPage(
                    id=f"page_{uuid4().hex}",
                    task_id=task.id,
                    page_number=page_number,
                )
            page.text = f"Page {page_number} extracted placeholder text"
            page.metadata_json = {
                "source": "offline_parser",
                "block_count": result.parse_summary.block_count,
            }
            db_session.add(page)
        return _parse_summary_payload(result)

    def _step_detect_tables_and_figures(self, db_session, context: dict) -> dict:
        result = context["analysis_result"]
        return {
            "table_count": result.parse_summary.table_count,
            "figure_count": 0,
        }

    def _step_render_candidate_pages(self, db_session, context: dict) -> dict:
        task = context["task"]
        pages = (
            db_session.query(DocumentPage)
            .filter_by(task_id=task.id)
            .order_by(DocumentPage.page_number)
            .all()
        )
        created = 0
        for page in pages[: min(3, len(pages))]:
            artifact = PageArtifact(
                id=f"artifact_{uuid4().hex}",
                task_id=task.id,
                page_id=page.id,
                artifact_type="page_render_placeholder",
                storage_uri=f"artifact://{task.id}/page-{page.page_number}.txt",
                payload={"page_number": page.page_number},
            )
            db_session.add(artifact)
            created += 1
        return {"artifact_count": created}

    def _step_vision_understanding(self, db_session, context: dict) -> dict:
        result = context["analysis_result"]
        return {
            "fallback": True,
            "table_count": result.parse_summary.table_count,
        }

    def _step_build_evidence_units(self, db_session, context: dict) -> dict:
        task = context["task"]
        result = context["analysis_result"]
        evidence_count = max(1, min(result.parse_summary.evidence_unit_count, 8))
        for index in range(evidence_count):
            source_ref = f"offline:{index + 1}"
            evidence = (
                db_session.query(EvidenceUnit)
                .filter_by(
                    task_id=task.id,
                    source_type="offline_pdf",
                    source_ref=source_ref,
                )
                .one_or_none()
            )
            if evidence is None:
                evidence = EvidenceUnit(
                    id=f"evidence_{uuid4().hex}",
                    task_id=task.id,
                    source_type="offline_pdf",
                    source_ref=source_ref,
                )
            evidence.page_number = index + 1
            evidence.category = "commercial_progress"
            evidence.content = f"Offline evidence unit {index + 1}"
            evidence.structured_data = {"source": "offline_pipeline"}
            evidence.confidence_score = 0.6
            db_session.add(evidence)
        return {"evidence_unit_count": evidence_count}

    def _step_score_and_judge(self, db_session, context: dict) -> dict:
        result = context["analysis_result"]
        self._write_score(db_session, task_id=context["task"].id, result=result)
        return {
            "potential_score": result.score_result.potential_score,
        }

    def _step_assemble_report(self, db_session, context: dict) -> dict:
        self._write_report(
            db_session,
            task_id=context["task"].id,
            file=context["file"],
            result=context["analysis_result"],
        )
        return {"report_status": "ready"}

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
