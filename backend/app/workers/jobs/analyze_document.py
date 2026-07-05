from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.analysis.pipeline import PIPELINE_STEP_NAMES
from app.domain.scoring.dimensions import SCORING_DIMENSIONS
from app.domain.tasks.state_machine import StepStatus, TaskStatus, can_retry_step
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
)
from app.infrastructure.pdf_tools.reader import extract_page_texts
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
                task.status = (
                    TaskStatus.QUEUED.value
                    if _has_retrying_step(db_session, task_id=task_id)
                    else TaskStatus.FAILED.value
                )
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
        step.attempt_count = (step.attempt_count or 0) + 1
        step.error_message = None
        step.payload = {
            "order": order,
            "completed": False,
            "attempt_count": step.attempt_count,
        }
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
            retry_available = can_retry_step(
                StepStatus.FAILED,
                attempt_count=step.attempt_count or 0,
                max_attempts=step.max_attempts or 1,
            )
            step.status = (
                StepStatus.RETRYING.value
                if retry_available
                else StepStatus.FAILED.value
            )
            step.error_message = str(exc)
            step.payload = {
                "order": order,
                "completed": False,
                "attempt_count": step.attempt_count,
                "retry_available": retry_available,
            }
            db_session.add(step)
            db_session.commit()
            raise

        step = (
            db_session.query(TaskStep)
            .filter_by(task_id=task_id, step_name=step_name)
            .one()
        )
        step.status = StepStatus.SUCCEEDED.value
        step.payload = {
            "order": order,
            "completed": True,
            "attempt_count": step.attempt_count,
            **(payload or {}),
        }
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
        extracted_pages = extract_page_texts(context["pdf_path"], page_count=page_count)
        for page_text in extracted_pages:
            page = (
                db_session.query(DocumentPage)
                .filter_by(task_id=task.id, page_number=page_text.page_number)
                .one_or_none()
            )
            if page is None:
                page = DocumentPage(
                    id=f"page_{uuid4().hex}",
                    task_id=task.id,
                    page_number=page_text.page_number,
                )
            page.text = page_text.text
            page.metadata_json = {
                "source": "offline_parser",
                "text_status": page_text.status,
                "block_count": result.parse_summary.block_count,
                "text_extraction": page_text.metadata,
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
                artifact_type="page_render_summary",
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
        evidence_count = 0
        for index, dimension in enumerate(SCORING_DIMENSIONS):
            source_ref = f"offline:{dimension.key}"
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
            evidence.page_number = min(index + 1, result.parse_summary.page_count)
            evidence.category = dimension.required_category
            evidence.content = f"BP 中存在与「{dimension.name}」相关的候选材料。"
            evidence.structured_data = {
                "source": "offline_pipeline",
                "dimension_key": dimension.key,
                "dimension_name": dimension.name,
            }
            evidence.confidence_score = 0.6
            db_session.add(evidence)
            evidence_count += 1
        return {"evidence_unit_count": evidence_count}

    def _step_score_and_judge(self, db_session, context: dict) -> dict:
        result = context["analysis_result"]
        dimensions = self._write_score(db_session, task_id=context["task"].id, result=result)
        context["score_dimensions"] = dimensions
        return {
            "potential_score": sum(dimension["score"] for dimension in dimensions),
            "dimension_count": len(dimensions),
        }

    def _step_assemble_report(self, db_session, context: dict) -> dict:
        self._write_report(
            db_session,
            task_id=context["task"].id,
            file=context["file"],
            result=context["analysis_result"],
        )
        return {"report_status": "ready"}

    def _write_score(self, db_session, *, task_id: str, result) -> list[dict]:
        score = db_session.query(ScoreResult).filter_by(task_id=task_id).one_or_none()
        if score is None:
            score = ScoreResult(id=f"score_{task_id}", task_id=task_id)
        dimensions = _build_dimension_scores(
            db_session,
            task_id=task_id,
            result=result,
        )
        total_score = round(sum(dimension["score"] for dimension in dimensions), 2)
        score.total_score = total_score
        score.score_payload = {
            "potential_score": total_score,
            "dimensions": dimensions,
            "parse_summary": _parse_summary_payload(result),
        }
        db_session.add(score)
        _write_judgment_cards(db_session, task_id=task_id, dimensions=dimensions)
        return dimensions

    def _write_report(self, db_session, *, task_id: str, file: File, result) -> None:
        report = db_session.query(Report).filter_by(task_id=task_id).one_or_none()
        if report is None:
            report = Report(id=f"report_{task_id}", task_id=task_id)
        score = db_session.query(ScoreResult).filter_by(task_id=task_id).one_or_none()
        score_payload = score.score_payload if score is not None else {}
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
                "potential_score": score_payload.get("potential_score"),
                "dimensions": score_payload.get("dimensions", []),
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


def _has_retrying_step(db_session, *, task_id: str) -> bool:
    return (
        db_session.query(TaskStep)
        .filter_by(task_id=task_id, status=StepStatus.RETRYING.value)
        .first()
        is not None
    )


def _build_dimension_scores(db_session, *, task_id: str, result) -> list[dict]:
    evidence_units = db_session.query(EvidenceUnit).filter_by(task_id=task_id).all()
    evidence_by_category: dict[str, list[EvidenceUnit]] = {}
    for evidence in evidence_units:
        if evidence.category:
            evidence_by_category.setdefault(evidence.category, []).append(evidence)

    dimensions = []
    for dimension in SCORING_DIMENSIONS:
        related_evidence = evidence_by_category.get(dimension.required_category or "", [])
        evidence_refs = [
            {
                "id": evidence.id,
                "source_ref": evidence.source_ref,
                "page_number": evidence.page_number,
                "confidence_score": evidence.confidence_score,
            }
            for evidence in related_evidence[:3]
        ]
        score = _score_dimension(
            max_score=dimension.max_score,
            evidence_count=len(related_evidence),
            table_count=result.parse_summary.table_count,
            page_count=result.parse_summary.page_count,
        )
        guidance = _DIMENSION_GUIDANCE[dimension.key]
        dimensions.append(
            {
                "key": dimension.key,
                "name": dimension.name,
                "score": score,
                "max_score": dimension.max_score,
                "reason": _dimension_reason(
                    dimension_name=dimension.name,
                    score=score,
                    max_score=dimension.max_score,
                    evidence_count=len(related_evidence),
                ),
                "evidence_refs": evidence_refs,
                "suggestions_for_bp": guidance["suggestions_for_bp"],
                "due_diligence_questions": guidance["due_diligence_questions"],
            }
        )
    return dimensions


def _score_dimension(
    *,
    max_score: float,
    evidence_count: int,
    table_count: int,
    page_count: int,
) -> float:
    if evidence_count <= 0:
        return 0.0
    evidence_ratio = min(1.0, evidence_count / 2)
    richness_ratio = min(1.0, (table_count + page_count) / 20)
    score_ratio = 0.55 + 0.25 * evidence_ratio + 0.2 * richness_ratio
    return round(max_score * min(score_ratio, 1.0), 2)


def _dimension_reason(
    *,
    dimension_name: str,
    score: float,
    max_score: float,
    evidence_count: int,
) -> str:
    if evidence_count <= 0:
        return f"未检索到与「{dimension_name}」直接相关的结构化证据，因此该项暂不计分。"
    if score >= max_score * 0.8:
        return f"已检索到与「{dimension_name}」相关的候选证据，材料完整度较好，按当前离线规则给出较高分。"
    return f"已检索到与「{dimension_name}」相关的候选证据，但证据强度和结构化程度仍需人工复核。"


def _write_judgment_cards(db_session, *, task_id: str, dimensions: list[dict]) -> None:
    for dimension in dimensions:
        card = (
            db_session.query(JudgmentCard)
            .filter_by(task_id=task_id, dimension_key=dimension["key"])
            .one_or_none()
        )
        if card is None:
            card = JudgmentCard(
                id=f"judgment_{task_id}_{dimension['key']}",
                task_id=task_id,
                dimension_key=dimension["key"],
            )
        card.verdict = _verdict_for_score(
            score=dimension["score"],
            max_score=dimension["max_score"],
        )
        card.rationale = dimension["reason"]
        card.evidence_refs = dimension["evidence_refs"]
        card.payload = {
            "score": dimension["score"],
            "max_score": dimension["max_score"],
            "suggestions_for_bp": dimension["suggestions_for_bp"],
            "due_diligence_questions": dimension["due_diligence_questions"],
        }
        db_session.add(card)


def _verdict_for_score(*, score: float, max_score: float) -> str:
    ratio = score / max_score if max_score else 0
    if ratio >= 0.8:
        return "strong"
    if ratio >= 0.6:
        return "acceptable"
    if ratio > 0:
        return "weak"
    return "missing"


_DIMENSION_GUIDANCE = {
    "problem_need_strength": {
        "suggestions_for_bp": [
            "补充客户访谈、政策文件、行业报告等客观证据，证明痛点真实存在。",
            "说明痛点的紧迫程度、影响范围和现有替代方案不足。",
        ],
        "due_diligence_questions": [
            "访谈目标客户，确认痛点是否高频且有预算解决。",
            "核验 BP 中引用的政策、调研和客户反馈来源。",
        ],
    },
    "market_attractiveness": {
        "suggestions_for_bp": [
            "补充细分市场规模、增速、渗透率和国产化率等强相关数据。",
            "优先引用头部咨询机构、协会或招股书等权威来源。",
        ],
        "due_diligence_questions": [
            "复核市场规模口径是否与项目真实业务边界一致。",
            "比较目标客户订单和行业增速是否匹配。",
        ],
    },
    "product_solution": {
        "suggestions_for_bp": [
            "清晰说明产品如何回应前述痛点，以及核心竞争力来自哪里。",
            "补充产品成熟度、稳定供应能力和竞品对比。",
        ],
        "due_diligence_questions": [
            "验证产品 demo、交付记录和关键技术指标。",
            "访谈客户确认产品优势是否真实可感知。",
        ],
    },
    "business_model_unit_economics": {
        "suggestions_for_bp": [
            "说明客户类型、收费模式、销售周期和回款方式。",
            "补充毛利率、获客成本、客单价和复购等单位经济指标。",
        ],
        "due_diligence_questions": [
            "抽查合同和发票，确认收入确认方式。",
            "测算规模化后毛利和现金流是否可持续。",
        ],
    },
    "team_fit": {
        "suggestions_for_bp": [
            "补充核心团队研发、市场、产业资源和过往业绩。",
            "突出创始人或核心团队与当前赛道的匹配度。",
        ],
        "due_diligence_questions": [
            "核验核心成员履历、股权稳定性和分工。",
            "评估团队短板是否需要通过招聘或顾问补足。",
        ],
    },
    "commercialization_progress": {
        "suggestions_for_bp": [
            "补充产品研发、客户验证、订单、产能和认证进展。",
            "提供过往三年财务数据和未来三年收入利润预测。",
        ],
        "due_diligence_questions": [
            "核验客户订单、验收单、回款和在手 pipeline。",
            "确认产能建设、认证节点和规模交付风险。",
        ],
    },
    "competition_barriers": {
        "suggestions_for_bp": [
            "列出国内外竞对和对标上市公司，说明差异化定位。",
            "突出资质、数据、渠道、工艺、先发优势等核心壁垒。",
        ],
        "due_diligence_questions": [
            "访谈行业专家，判断壁垒是否可持续。",
            "比较竞品价格、性能、渠道和客户重叠度。",
        ],
    },
    "financing_logic_use_of_funds": {
        "suggestions_for_bp": [
            "明确融资金额、估值逻辑、资金用途和阶段目标。",
            "说明后续融资、上市或并购退出路径。",
        ],
        "due_diligence_questions": [
            "核验资金用途是否匹配当前阶段和未来里程碑。",
            "评估估值、融资节奏和退出预期是否合理。",
        ],
    },
}
