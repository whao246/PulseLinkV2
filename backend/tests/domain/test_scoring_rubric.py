from app.domain.scoring.dimensions import SCORING_DIMENSIONS
from app.domain.scoring.rubric import baseline_score_allowed


def test_scoring_dimensions_sum_to_100():
    assert sum(d.max_score for d in SCORING_DIMENSIONS) == 100


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
