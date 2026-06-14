from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScoringDimension:
    key: str
    name: str
    max_score: float
    required_category: str | None = None


SCORING_DIMENSIONS: tuple[ScoringDimension, ...] = (
    ScoringDimension("problem_need_strength", "问题与需求强度", 10, "problem"),
    ScoringDimension("market_attractiveness", "市场空间与赛道吸引力", 10, "market"),
    ScoringDimension("product_solution", "产品与解决方案", 12.5, "product"),
    ScoringDimension(
        "business_model_unit_economics",
        "商业模式与单位经济",
        12.5,
        "business_model",
    ),
    ScoringDimension("team_fit", "团队匹配度", 15, "team"),
    ScoringDimension("commercialization_progress", "商业化进展", 15, "commercialization"),
    ScoringDimension("competition_barriers", "竞争格局与壁垒", 15, "competition"),
    ScoringDimension("financing_logic_use_of_funds", "融资逻辑与资金用途", 10, "funding"),
)
