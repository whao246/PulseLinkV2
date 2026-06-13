import pytest

from app.domain.analysis.evidence import EvidenceSourceType, EvidenceUnit


def test_evidence_unit_accepts_valid_page_number_and_source_type():
    evidence = EvidenceUnit(
        id="evidence-1",
        task_id="task-1",
        page_number=3,
        source_type=EvidenceSourceType.TEXT,
        source_ref="page:3:block:2",
        category="market",
        content="Market size is growing.",
        structured_data={"metric": "market_size"},
        confidence_score=0.82,
    )

    assert evidence.page_number == 3
    assert evidence.source_type == EvidenceSourceType.TEXT


def test_evidence_unit_rejects_invalid_confidence():
    with pytest.raises(ValueError, match="confidence_score"):
        EvidenceUnit(
            id="evidence-1",
            task_id="task-1",
            page_number=1,
            source_type=EvidenceSourceType.TABLE,
            source_ref="page:1:table:1",
            category="financials",
            content="Revenue table.",
            structured_data={"rows": []},
            confidence_score=1.5,
        )


def test_evidence_unit_rejects_invalid_page_number():
    with pytest.raises(ValueError, match="page_number"):
        EvidenceUnit(
            id="evidence-1",
            task_id="task-1",
            page_number=0,
            source_type=EvidenceSourceType.TEXT,
            source_ref="page:0:block:1",
            category="market",
            content="Market size is growing.",
            structured_data={},
            confidence_score=0.5,
        )


def test_evidence_unit_rejects_blank_content():
    with pytest.raises(ValueError, match="content"):
        EvidenceUnit(
            id="evidence-1",
            task_id="task-1",
            page_number=1,
            source_type=EvidenceSourceType.TEXT,
            source_ref="page:1:block:1",
            category="market",
            content="  ",
            structured_data={},
            confidence_score=0.5,
        )


def test_evidence_unit_structured_data_is_top_level_immutable():
    evidence = EvidenceUnit(
        id="evidence-1",
        task_id="task-1",
        page_number=1,
        source_type=EvidenceSourceType.TEXT,
        source_ref="page:1:block:1",
        category="market",
        content="Market size is growing.",
        structured_data={"x": 1},
        confidence_score=0.5,
    )

    with pytest.raises(TypeError):
        evidence.structured_data["x"] = 2
