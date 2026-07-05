import pytest

from app.domain.scoring.dimensions import SCORING_DIMENSIONS
from app.domain.scoring.rubric import SCORING_RUBRICS, baseline_score_allowed


def test_scoring_dimensions_sum_to_100():
    assert sum(d.max_score for d in SCORING_DIMENSIONS) == pytest.approx(100)


def test_problem_dimension_fails_baseline_without_problem_evidence():
    allowed = baseline_score_allowed(
        dimension_key="problem_need_strength",
        evidence_categories={"market", "team"},
    )

    assert allowed is False


def test_market_dimension_fails_baseline_without_market_evidence():
    allowed = baseline_score_allowed(
        dimension_key="market_attractiveness",
        evidence_categories={"problem", "team"},
    )

    assert allowed is False


def test_baseline_allows_score_when_required_evidence_exists():
    allowed = baseline_score_allowed(
        dimension_key="product_solution",
        evidence_categories={"product"},
    )

    assert allowed is True


def test_unknown_dimension_key_raises_clear_error():
    with pytest.raises(ValueError, match="unknown scoring dimension.*not_a_dimension"):
        baseline_score_allowed(
            dimension_key="not_a_dimension",
            evidence_categories={"product"},
        )


def test_all_dimensions_have_required_category():
    assert all(d.required_category for d in SCORING_DIMENSIONS)


def test_rubrics_capture_required_scoring_rules():
    assert set(SCORING_RUBRICS) == {dimension.key for dimension in SCORING_DIMENSIONS}
    assert "没有问题和痛点的描述，该项不及格" in SCORING_RUBRICS[
        "problem_need_strength"
    ].deduction_logic
    assert "没有市场规模数据，该项不及格" in SCORING_RUBRICS[
        "market_attractiveness"
    ].deduction_logic
    assert "项目方要在BP中补充的资料" in SCORING_RUBRICS[
        "commercialization_progress"
    ].suggestion_policy
    assert "建议投资方尽调的方向和内容" in SCORING_RUBRICS[
        "commercialization_progress"
    ].suggestion_policy
