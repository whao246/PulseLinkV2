import pytest

from app.domain.analysis.evidence import EvidenceSourceType, EvidenceUnit


def test_evidence_unit_requires_page_number():
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
