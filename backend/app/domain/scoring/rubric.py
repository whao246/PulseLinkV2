from __future__ import annotations

from app.domain.scoring.dimensions import SCORING_DIMENSIONS


DIMENSION_BY_KEY = {dimension.key: dimension for dimension in SCORING_DIMENSIONS}


def baseline_score_allowed(*, dimension_key: str, evidence_categories: set[str]) -> bool:
    try:
        dimension = DIMENSION_BY_KEY[dimension_key]
    except KeyError as exc:
        raise ValueError(f"unknown scoring dimension: {dimension_key}") from exc

    if dimension.required_category is None:
        return True
    return dimension.required_category in evidence_categories
