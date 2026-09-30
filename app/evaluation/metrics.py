from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.evaluation.models import EvaluationCase, EvaluationRecord, EvaluationSummary
from app.schemas.domain import NodeMetric


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def route_scores(expected: list[str], actual: list[str]) -> tuple[float, float]:
    expected_set = set(expected)
    actual_set = set(actual)
    common = expected_set & actual_set
    precision = len(common) / len(actual_set) if actual_set else 0.0
    recall = len(common) / len(expected_set) if expected_set else 1.0
    return precision, recall


def build_record(
    *,
    run_id: str,
    case: EvaluationCase,
    result: Mapping[str, Any],
    router_mode: str,
    model_backend: str,
    search_backend: str,
) -> EvaluationRecord:
    actual_route = _unique(list(result.get("route_history", [])))
    expected = _unique(case.expected_agents)
    precision, recall = route_scores(expected, actual_route)
    metrics = [NodeMetric.model_validate(item) for item in result.get("metrics", [])]
    missing_outputs = [name for name in case.required_outputs if not result.get(name)]
    source_count = len(result.get("sources", []))
    task_success = (
        result.get("status") == "completed"
        and not missing_outputs
        and (not case.requires_sources or source_count > 0)
    )
    return EvaluationRecord(
        run_id=run_id,
        case_id=case.id,
        router_mode=router_mode,
        model_backend=model_backend,
        search_backend=search_backend,
        status=str(result.get("status", "unknown")),
        expected_agents=expected,
        actual_route=actual_route,
        route_precision=round(precision, 4),
        route_recall=round(recall, 4),
        exact_route_match=set(expected) == set(actual_route),
        redundant_agents=sorted(set(actual_route) - set(expected)),
        missing_agents=sorted(set(expected) - set(actual_route)),
        task_success=task_success,
        missing_outputs=missing_outputs,
        source_count=source_count,
        error_count=len(result.get("errors", [])),
        total_latency_ms=sum(metric.latency_ms for metric in metrics),
        token_usage=sum(metric.token_usage for metric in metrics),
        node_metrics=metrics,
    )


def summarize(records: list[EvaluationRecord]) -> EvaluationSummary:
    if not records:
        raise ValueError("at least one evaluation record is required")
    count = len(records)
    return EvaluationSummary(
        router_mode=records[0].router_mode,
        cases=count,
        task_success_rate=sum(record.task_success for record in records) / count,
        average_route_precision=sum(record.route_precision for record in records) / count,
        average_route_recall=sum(record.route_recall for record in records) / count,
        exact_route_match_rate=sum(record.exact_route_match for record in records) / count,
        average_latency_ms=sum(record.total_latency_ms for record in records) / count,
        average_token_usage=sum(record.token_usage for record in records) / count,
    )
