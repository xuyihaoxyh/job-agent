from __future__ import annotations

from pathlib import Path

import pytest

from app.evaluation.metrics import (
    build_record,
    evaluate_assertion,
    route_scores,
    summarize,
)
from app.evaluation.models import EvaluationAssertion, EvaluationCase


def test_evaluation_dataset_is_valid():
    path = Path(__file__).parents[1] / "evaluations" / "cases.json"
    cases = [EvaluationCase.model_validate_json(item) for item in _json_items(path)]

    assert len(cases) >= 20
    assert {case.category for case in cases} >= {
        "company",
        "salary",
        "match",
        "comprehensive",
    }
    assert len({case.id for case in cases}) == len(cases)


def _json_items(path: Path) -> list[str]:
    import json

    return [json.dumps(item, ensure_ascii=False) for item in json.loads(path.read_text())]


def test_route_scores_show_fixed_router_redundancy():
    expected = ["intake", "company", "report"]
    actual = ["intake", "jd", "company", "salary", "match", "report"]

    precision, recall = route_scores(expected, actual)

    assert precision == pytest.approx(0.5)
    assert recall == 1.0


def test_build_record_and_summary():
    case = EvaluationCase(
        id="company-only",
        category="company",
        description="company lookup",
        request={},
        expected_agents=["intake", "company", "report"],
        forbidden_agents=["salary", "match"],
        required_outputs=["company_info", "final_report"],
        requires_sources=True,
        required_source_outputs=["company_info"],
        assertions=[
            EvaluationAssertion(
                path="company_info.summary",
                operator="contains",
                expected="example",
            )
        ],
    )
    result = {
        "status": "completed",
        "route_history": ["intake", "jd", "company", "salary", "match", "report"],
        "company_info": {
            "summary": "example",
            "sources": [{"url": "https://example.com"}],
        },
        "final_report": "done",
        "sources": [{"url": "https://example.com"}],
        "metrics": [
            {
                "node": "company",
                "latency_ms": 20,
                "token_usage": 1250,
                "input_tokens": 1000,
                "output_tokens": 250,
                "model_calls": 1,
            }
        ],
        "elapsed_ms": 14,
        "errors": [],
    }

    record = build_record(
        run_id="run-1",
        case=case,
        result=result,
        router_mode="fixed",
        model_backend="mock",
        search_backend="static",
        input_price_per_million=0.40,
        output_price_per_million=1.60,
    )
    summary = summarize([record])

    assert record.task_success is True
    assert record.redundant_agents == ["jd", "match", "salary"]
    assert record.forbidden_agents_hit == ["match", "salary"]
    assert record.route_precision == 0.5
    assert record.route_f1 == pytest.approx(0.6667)
    assert record.assertion_accuracy == 1.0
    assert record.input_tokens == 1000
    assert record.output_tokens == 250
    assert record.model_calls == 1
    assert record.estimated_cost_usd == pytest.approx(0.0008)
    assert summary.task_success_rate == 1.0
    assert summary.forbidden_agent_violation_rate == 1.0
    assert summary.assertion_accuracy == 1.0
    assert summary.average_latency_ms == 14
    assert summary.p50_latency_ms == 14
    assert summary.p95_latency_ms == 14
    assert summary.total_input_tokens == 1000
    assert summary.total_output_tokens == 250
    assert summary.total_model_calls == 1
    assert summary.total_estimated_cost_usd == pytest.approx(0.0008)


def test_old_evaluation_record_without_model_name_is_compatible():
    from app.evaluation.models import EvaluationRecord

    payload = {
        "run_id": "old-run",
        "case_id": "old-case",
        "router_mode": "fixed",
        "model_backend": "mock",
        "search_backend": "static",
        "status": "completed",
        "expected_agents": [],
        "actual_route": [],
        "route_precision": 0,
        "route_recall": 1,
        "route_f1": 0,
        "exact_route_match": True,
        "task_success": True,
    }

    record = EvaluationRecord.model_validate(payload)

    assert record.model_name == "unknown"


def test_route_scores_penalize_repeated_agent_calls():
    expected = ["intake", "jd", "salary", "report"]
    actual = ["intake", "jd", "salary", "salary", "report"]

    precision, recall = route_scores(expected, actual)

    assert precision == pytest.approx(0.8)
    assert recall == 1.0


def test_required_sources_must_belong_to_the_requested_output():
    case = EvaluationCase(
        id="company-only",
        category="company",
        description="company lookup",
        request={},
        expected_agents=["company"],
        required_outputs=["company_info"],
        requires_sources=True,
        required_source_outputs=["company_info"],
    )
    record = build_record(
        run_id="run-1",
        case=case,
        result={
            "status": "completed",
            "route_history": ["company"],
            "company_info": {"summary": "unknown", "sources": []},
            "salary_info": {"sources": [{"url": "https://example.com"}]},
            "sources": [{"url": "https://example.com"}],
            "elapsed_ms": 10,
        },
        router_mode="fixed",
        model_backend="mock",
        search_backend="static",
    )

    assert record.task_success is False
    assert record.missing_source_outputs == ["company_info"]


@pytest.mark.parametrize(
    ("assertion", "passed"),
    [
        (EvaluationAssertion(path="match.score", operator="equals", expected=82), True),
        (
            EvaluationAssertion(
                path="match.skills",
                operator="contains_all",
                expected=["Java", "Redis"],
            ),
            True,
        ),
        (
            EvaluationAssertion(
                path="report", operator="not_contains", expected="上市公司"
            ),
            True,
        ),
        (
            EvaluationAssertion(path="match.score", operator="between", expected=[80, 90]),
            True,
        ),
        (EvaluationAssertion(path="company.sources", operator="is_empty"), True),
        (EvaluationAssertion(path="report", operator="not_empty"), True),
    ],
)
def test_evaluate_assertion(assertion, passed):
    result = {
        "match": {"score": 82, "skills": ["Java", "Redis"]},
        "company": {"sources": []},
        "report": "信息不足",
    }

    assert evaluate_assertion(result, assertion).passed is passed


def test_grounded_claim_rate_requires_valid_source_ids():
    case = EvaluationCase(
        id="grounding",
        category="company",
        description="grounding",
        request={},
        expected_agents=["company"],
        required_outputs=["company_info"],
    )
    record = build_record(
        run_id="run-1",
        case=case,
        result={
            "status": "completed",
            "route_history": ["company"],
            "company_info": {
                "summary": "example",
                "sources": [{"id": "source-1"}],
                "evidence": [
                    {"claim": "supported", "source_ids": ["source-1"]},
                    {"claim": "unsupported", "source_ids": ["missing"]},
                ],
            },
        },
        router_mode="fixed",
        model_backend="mock",
        search_backend="static",
    )

    assert record.grounded_claim_rate == 0.5
