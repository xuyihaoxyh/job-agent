from __future__ import annotations

from pathlib import Path

import pytest

from app.evaluation.metrics import build_record, route_scores, summarize
from app.evaluation.models import EvaluationCase


def test_evaluation_dataset_is_valid():
    path = Path(__file__).parents[1] / "evaluations" / "cases.json"
    cases = [EvaluationCase.model_validate_json(item) for item in _json_items(path)]

    assert len(cases) >= 5
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
    )
    result = {
        "status": "completed",
        "route_history": ["intake", "jd", "company", "salary", "match", "report"],
        "company_info": {"summary": "example"},
        "final_report": "done",
        "sources": [{"url": "https://example.com"}],
        "metrics": [{"node": "company", "latency_ms": 20, "token_usage": 0}],
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
    assert summary.average_latency_ms == 20
