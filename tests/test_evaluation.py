from __future__ import annotations

from pathlib import Path

import pytest

from app.evaluation.metrics import build_record, route_scores, summarize
from app.evaluation.models import EvaluationCase


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
        required_outputs=["company_info", "final_report"],
        requires_sources=True,
        required_source_outputs=["company_info"],
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
        "metrics": [{"node": "company", "latency_ms": 20, "token_usage": 0}],
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
    )
    summary = summarize([record])

    assert record.task_success is True
    assert record.redundant_agents == ["jd", "match", "salary"]
    assert record.route_precision == 0.5
    assert summary.task_success_rate == 1.0
    assert summary.average_latency_ms == 14


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
