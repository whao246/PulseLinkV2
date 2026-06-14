from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy import UniqueConstraint

from app.infrastructure.db.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String(64), primary_key=True)
    email = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


class File(Base):
    __tablename__ = "files"
    __table_args__ = (UniqueConstraint("user_id", "sha256", name="uq_files_user_sha256"),)

    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=False)
    sha256 = Column(String(64), nullable=False)
    filename = Column(String(512), nullable=False)
    content_type = Column(String(255), nullable=True)
    size_bytes = Column(Integer, nullable=True)
    storage_uri = Column(Text, nullable=False)
    metadata_json = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, nullable=True)


class AnalysisTask(Base):
    __tablename__ = "analysis_tasks"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_tasks_user_idempotency"),
    )

    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=False)
    file_id = Column(String(64), ForeignKey("files.id"), nullable=True)
    idempotency_key = Column(String(255), nullable=False)
    task_type = Column(String(64), nullable=False)
    model_profile = Column(String(128), nullable=True)
    status = Column(String(64), nullable=False)
    options = Column(JSON, nullable=True)
    payload = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


class TaskStep(Base):
    __tablename__ = "task_steps"
    __table_args__ = (
        UniqueConstraint("task_id", "step_name", name="uq_task_steps_task_step"),
    )

    id = Column(String(64), primary_key=True)
    task_id = Column(String(64), ForeignKey("analysis_tasks.id"), nullable=False)
    step_name = Column(String(128), nullable=False)
    status = Column(String(64), nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    locked_until = Column(DateTime, nullable=True)
    attempt_count = Column(Integer, nullable=True)
    max_attempts = Column(Integer, nullable=True)
    progress_payload = Column(JSON, nullable=True)
    payload = Column(JSON, nullable=True)
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)


class DocumentPage(Base):
    __tablename__ = "document_pages"
    __table_args__ = (
        UniqueConstraint("task_id", "page_number", name="uq_document_pages_task_page"),
    )

    id = Column(String(64), primary_key=True)
    task_id = Column(String(64), ForeignKey("analysis_tasks.id"), nullable=False)
    page_number = Column(Integer, nullable=False)
    text = Column(Text, nullable=True)
    width = Column(Float, nullable=True)
    height = Column(Float, nullable=True)
    metadata_json = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, nullable=True)


class PageArtifact(Base):
    __tablename__ = "page_artifacts"

    id = Column(String(64), primary_key=True)
    task_id = Column(String(64), ForeignKey("analysis_tasks.id"), nullable=False)
    page_id = Column(String(64), ForeignKey("document_pages.id"), nullable=False)
    artifact_type = Column(String(64), nullable=False)
    storage_uri = Column(Text, nullable=False)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=True)


class EvidenceUnit(Base):
    __tablename__ = "evidence_units"
    __table_args__ = (
        UniqueConstraint(
            "task_id",
            "source_type",
            "source_ref",
            name="uq_evidence_units_source",
        ),
    )

    id = Column(String(64), primary_key=True)
    task_id = Column(String(64), ForeignKey("analysis_tasks.id"), nullable=False)
    source_type = Column(String(64), nullable=False)
    source_ref = Column(String(255), nullable=False)
    page_number = Column(Integer, nullable=True)
    category = Column(String(64), nullable=True)
    content = Column(Text, nullable=True)
    structured_data = Column(JSON, nullable=True)
    confidence_score = Column(Float, nullable=True)
    quote = Column(Text, nullable=True)
    normalized_text = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=True)


class FactCard(Base):
    __tablename__ = "fact_cards"
    __table_args__ = (
        UniqueConstraint("task_id", "dimension_key", name="uq_fact_cards_task_dimension"),
    )

    id = Column(String(64), primary_key=True)
    task_id = Column(String(64), ForeignKey("analysis_tasks.id"), nullable=False)
    dimension_key = Column(String(128), nullable=False)
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=True)
    evidence_refs = Column(JSON, nullable=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=True)


class JudgmentCard(Base):
    __tablename__ = "judgment_cards"
    __table_args__ = (
        UniqueConstraint(
            "task_id",
            "dimension_key",
            name="uq_judgment_cards_task_dimension",
        ),
    )

    id = Column(String(64), primary_key=True)
    task_id = Column(String(64), ForeignKey("analysis_tasks.id"), nullable=False)
    dimension_key = Column(String(128), nullable=False)
    verdict = Column(String(64), nullable=False)
    rationale = Column(Text, nullable=True)
    evidence_refs = Column(JSON, nullable=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=True)


class ScoreResult(Base):
    __tablename__ = "score_results"
    __table_args__ = (UniqueConstraint("task_id", name="uq_score_results_task"),)

    id = Column(String(64), primary_key=True)
    task_id = Column(String(64), ForeignKey("analysis_tasks.id"), nullable=False)
    total_score = Column(Float, nullable=True)
    score_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=True)


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("task_id", name="uq_reports_task"),)

    id = Column(String(64), primary_key=True)
    task_id = Column(String(64), ForeignKey("analysis_tasks.id"), nullable=False)
    title = Column(String(255), nullable=False)
    status = Column(String(64), nullable=False)
    storage_uri = Column(Text, nullable=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=True)
