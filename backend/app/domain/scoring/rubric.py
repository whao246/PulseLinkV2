from __future__ import annotations

from dataclasses import dataclass

from app.domain.scoring.dimensions import SCORING_DIMENSIONS


DIMENSION_BY_KEY = {dimension.key: dimension for dimension in SCORING_DIMENSIONS}


@dataclass(frozen=True)
class ScoringRubric:
    dimension_key: str
    scoring_rules: tuple[str, ...]
    deduction_logic: str
    suggestion_policy: str
    suggestions_for_bp: tuple[str, ...]
    due_diligence_questions: tuple[str, ...]


REPORT_ORDER_RULE = "材料完整度放在项目潜力之前呈现。"
SUGGESTION_SPLIT_RULE = (
    "项目潜力里面的建议补什么，分为两部分：一是建议项目方要在BP中补充的资料，"
    "二是建议投资方尽调的方向和内容。"
)


SCORING_RUBRICS: dict[str, ScoringRubric] = {
    "problem_need_strength": ScoringRubric(
        dimension_key="problem_need_strength",
        scoring_rules=(
            "检索BP中是否有对要解决的问题和痛点的描述，有的话在该项给个及格。",
            "评估该问题痛点是否真实存在，确认BP中有相关证据证实真实性和紧迫程度，比如政策、客户调研信息等，如果有且完整，该项加分。",
        ),
        deduction_logic="没有问题和痛点的描述，该项不及格。",
        suggestion_policy="建议项目方要在BP中补充的资料围绕问题痛点是否真实存在和紧迫程度，客观证据即可；建议投资方尽调的方向和内容围绕痛点真实性、紧迫性和客户预算核验。",
        suggestions_for_bp=(
            "补充客户访谈、政策文件、行业报告等客观证据，证明痛点真实存在。",
            "说明痛点的紧迫程度、影响范围和现有替代方案不足。",
        ),
        due_diligence_questions=(
            "访谈目标客户，确认痛点是否高频且有预算解决。",
            "核验 BP 中引用的政策、调研和客户反馈来源。",
        ),
    ),
    "market_attractiveness": ScoringRubric(
        dimension_key="market_attractiveness",
        scoring_rules=(
            "市场空间不是越大越好，要有切实想象空间、高增速和合理渗透率。",
            "国产替代类型项目需要关注国产化率进展。",
            "市场规模预测要与项目所在细分领域强相关，并优先引用头部咨询机构等权威来源。",
        ),
        deduction_logic="没有市场规模数据，该项不及格。",
        suggestion_policy="建议项目方要在BP中补充的资料纯粹是三方客观市场数据，项目客户订单等信息不放在这部分；建议投资方尽调的方向和内容是复核市场口径、增速、渗透率和国产化率。",
        suggestions_for_bp=(
            "补充细分市场规模、增速、渗透率和国产化率等强相关数据。",
            "优先引用头部咨询机构、协会、招股书或监管文件等权威来源。",
        ),
        due_diligence_questions=(
            "复核市场规模口径是否与项目真实业务边界一致。",
            "核验市场增速、渗透率和国产替代率是否有独立第三方依据。",
        ),
    ),
    "product_solution": ScoringRubric(
        dimension_key="product_solution",
        scoring_rules=(
            "产品和解决方案的核心竞争力要有突出解释，并回应前面的痛点。",
            "评估产品与方案成熟度、稳定供应能力和可参考业务数据。",
            "与市场现有产品和方案对比，说明优势。",
            "清晰解释产品与解决方案是做什么的是及格线。",
        ),
        deduction_logic="未清晰解释产品与解决方案是做什么的，该项不应及格；优势、成熟度、竞品对比越完整越加分。",
        suggestion_policy="建议项目方要在BP中补充产品能力、成熟度、供应稳定性和竞品对比；建议投资方尽调的方向和内容是验证产品 demo、交付记录、客户反馈和关键技术指标。",
        suggestions_for_bp=(
            "清晰说明产品如何回应前述痛点，以及核心竞争力来自哪里。",
            "补充产品成熟度、稳定供应能力、业务数据和竞品对比。",
        ),
        due_diligence_questions=(
            "验证产品 demo、交付记录和关键技术指标。",
            "访谈客户确认产品优势是否真实可感知。",
        ),
    ),
    "business_model_unit_economics": ScoringRubric(
        dimension_key="business_model_unit_economics",
        scoring_rules=(
            "阐述清楚项目如何实现商业闭环、赚取利润。",
            "说明面对什么类型的客户以及如何创收。",
            "单位经济最好有相关表述，帮助评估毛利水平和商业闭环可行性。",
        ),
        deduction_logic="不能让人理解项目怎么创收或客户是谁，该项不应及格；单位经济、毛利、客单价、获客成本越完整越加分。",
        suggestion_policy="建议项目方要在BP中补充客户类型、收费模式、毛利、获客成本、客单价和复购；建议投资方尽调的方向和内容是核验合同、发票、回款和规模化盈利假设。",
        suggestions_for_bp=(
            "说明客户类型、收费模式、销售周期和回款方式。",
            "补充毛利率、获客成本、客单价和复购等单位经济指标。",
        ),
        due_diligence_questions=(
            "抽查合同和发票，确认收入确认方式。",
            "测算规模化后毛利和现金流是否可持续。",
        ),
    ),
    "team_fit": ScoringRubric(
        dimension_key="team_fit",
        scoring_rules=(
            "提取事实有偏差时要检查文件解析准确性。",
            "核心看团队是否有足够研发、市场和产业资源来支撑。",
            "要么有极强创始人，要么有豪华且平衡的核心团队。",
        ),
        deduction_logic="团队信息缺失、履历无法支撑当前赛道或解析事实明显有偏差，应明显扣分。",
        suggestion_policy="建议项目方要在BP中补充核心团队研发、市场、产业资源和过往业绩；建议投资方尽调的方向和内容是核验履历、分工、股权稳定性和关键短板。",
        suggestions_for_bp=(
            "补充核心团队研发、市场、产业资源和过往业绩。",
            "突出创始人或核心团队与当前赛道的匹配度。",
        ),
        due_diligence_questions=(
            "核验核心成员履历、股权稳定性和分工。",
            "评估团队短板是否需要通过招聘或顾问补足。",
        ),
    ),
    "commercialization_progress": ScoringRubric(
        dimension_key="commercialization_progress",
        scoring_rules=(
            "关注产品研发和客户验证进展、产能建设布局、客户订单数据。",
            "最好有过往三年财务数据和未来三年财务预测，主要看收入利润水平。",
            "不同行业还要呈现商业化里程碑，如医药认证、汽车车规级认证等。",
        ),
        deduction_logic="缺少研发、客户验证、订单、财务或行业关键里程碑时应扣分；数据越可核验越加分。",
        suggestion_policy="建议项目方要在BP中补充的资料包括商业化里程碑、订单、产能、认证、历史财务和预测；建议投资方尽调的方向和内容是核验订单、回款、验收、pipeline、认证和产能。",
        suggestions_for_bp=(
            "补充产品研发、客户验证、订单、产能和认证进展。",
            "提供过往三年财务数据和未来三年收入利润预测。",
        ),
        due_diligence_questions=(
            "核验客户订单、验收单、回款和在手 pipeline。",
            "确认产能建设、认证节点和规模交付风险。",
        ),
    ),
    "competition_barriers": ScoringRubric(
        dimension_key="competition_barriers",
        scoring_rules=(
            "壁垒不一定面面俱到，但定位要清晰，长板发挥到极致。",
            "BP 要突出核心壁垒，如资质壁垒、行业隐性壁垒、先发优势等。",
            "需要全球和国内竞争格局，列出竞对和对标上市公司，分析竞争优劣势。",
            "项目能清晰说明行业地位和优劣势，才能扬长避短。",
        ),
        deduction_logic="没有竞争格局、竞对、对标公司或核心壁垒说明，应明显扣分。",
        suggestion_policy="建议项目方要在BP中补充国内外竞对、对标上市公司、优劣势和核心壁垒；建议投资方尽调的方向和内容是访谈专家并比较竞品价格、性能、渠道和客户重叠度。",
        suggestions_for_bp=(
            "列出国内外竞对和对标上市公司，说明差异化定位。",
            "突出资质、数据、渠道、工艺、先发优势等核心壁垒。",
        ),
        due_diligence_questions=(
            "访谈行业专家，判断壁垒是否可持续。",
            "比较竞品价格、性能、渠道和客户重叠度。",
        ),
    ),
    "financing_logic_use_of_funds": ScoringRubric(
        dimension_key="financing_logic_use_of_funds",
        scoring_rules=(
            "说明为什么要融资、融资金额以及明确资金用途。",
            "考察融资阶段和资金用途是否匹配项目当前发展阶段以及企业估值。",
            "最好说明后续融资和上市资本化运作，让投资人有明确退出预期。",
        ),
        deduction_logic="未说明融资金额、资金用途或融资阶段匹配关系，应明显扣分。",
        suggestion_policy="建议项目方要在BP中补充融资金额、估值逻辑、资金用途、里程碑和退出路径；建议投资方尽调的方向和内容是核验资金用途、估值合理性、融资节奏和退出预期。",
        suggestions_for_bp=(
            "明确融资金额、估值逻辑、资金用途和阶段目标。",
            "说明后续融资、上市或并购退出路径。",
        ),
        due_diligence_questions=(
            "核验资金用途是否匹配当前阶段和未来里程碑。",
            "评估估值、融资节奏和退出预期是否合理。",
        ),
    ),
}


def baseline_score_allowed(*, dimension_key: str, evidence_categories: set[str]) -> bool:
    try:
        dimension = DIMENSION_BY_KEY[dimension_key]
    except KeyError as exc:
        raise ValueError(f"unknown scoring dimension: {dimension_key}") from exc

    if dimension.required_category is None:
        return True
    return dimension.required_category in evidence_categories
