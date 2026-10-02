from app.graph.routers.hybrid import fallback_plan, validate_plan
from app.schemas.domain import AnalysisPlan


def test_valid_plan_preserves_model_intent_and_order():
    decision = validate_plan(
        AnalysisPlan(required_agents=["salary", "match"], reason="user intent")
    )

    assert decision.proposed_agents == ["salary", "match"]
    assert decision.final_agents == ["salary", "match"]
    assert decision.overridden is False


def test_plan_validation_removes_duplicates():
    decision = validate_plan(
        AnalysisPlan(
            required_agents=["company", "company", "salary"],
            reason="duplicate model output",
        )
    )

    assert decision.final_agents == ["company", "salary"]
    assert decision.overridden is True
    assert "重复" in decision.policy_reason


def test_empty_plan_falls_back_to_full_analysis():
    decision = validate_plan(AnalysisPlan(required_agents=[], reason="nothing selected"))

    assert decision.proposed_agents == []
    assert decision.final_agents == ["company", "salary", "match"]
    assert decision.overridden is True
    assert "全量分析" in decision.policy_reason


def test_planner_failure_falls_back_to_full_analysis():
    decision = fallback_plan("provider unavailable")

    assert decision.final_agents == ["company", "salary", "match"]
    assert decision.overridden is True
    assert "Planner 调用失败" in decision.policy_reason
