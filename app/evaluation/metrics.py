from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from math import ceil
from typing import Any

from app.evaluation.models import (
    AssertionResult,
    EvaluationAssertion,
    EvaluationCase,
    EvaluationRecord,
    EvaluationSummary,
)
from app.schemas.domain import NodeMetric


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def route_scores(expected: list[str], actual: list[str]) -> tuple[float, float]:
    expected_counts = Counter(expected)
    actual_counts = Counter(actual)
    common = sum(
        min(count, actual_counts[node]) for node, count in expected_counts.items()
    )
    precision = common / len(actual) if actual else 0.0
    recall = common / len(expected) if expected else 1.0
    return precision, recall


def _route_f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _value_at_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if isinstance(current, Mapping):
            current = current.get(part)
        else:
            current = getattr(current, part, None)
        if current is None:
            break
    return current


def evaluate_assertion(
    result: Mapping[str, Any], assertion: EvaluationAssertion
) -> AssertionResult:
    actual = _value_at_path(result, assertion.path)
    expected = assertion.expected
    if assertion.operator == "equals":
        passed = actual == expected
    elif assertion.operator == "contains":
        passed = actual is not None and expected in actual
    elif assertion.operator == "not_contains":
        passed = actual is None or expected not in actual
    elif assertion.operator == "contains_all":
        passed = actual is not None and all(item in actual for item in expected or [])
    elif assertion.operator == "between":
        passed = (
            actual is not None
            and isinstance(expected, list)
            and len(expected) == 2
            and expected[0] <= actual <= expected[1]
        )
    elif assertion.operator == "is_empty":
        passed = not actual
    else:
        passed = bool(actual)
    return AssertionResult(
        path=assertion.path,
        operator=assertion.operator,
        expected=expected,
        actual=actual,
        passed=passed,
    )


def _grounded_claim_rate(result: Mapping[str, Any]) -> float | None:
    company = result.get("company_info")
    if company is None:
        return None
    evidence = _value_at_path(company, "evidence") or []
    if not evidence:
        return None
    sources = _value_at_path(company, "sources") or []
    valid_ids = {
        _value_at_path(source, "id") for source in sources if _value_at_path(source, "id")
    }
    grounded = 0
    for fact in evidence:
        source_ids = set(_value_at_path(fact, "source_ids") or [])
        if source_ids and source_ids <= valid_ids:
            grounded += 1
    return grounded / len(evidence)


def _percentile(values: list[int], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, ceil(percentile * len(ordered)) - 1)
    return float(ordered[index])


def _has_sources(value: Any) -> bool:
    if value is None:
        return False
    sources = value.get("sources", []) if isinstance(value, Mapping) else getattr(value, "sources", [])
    return bool(sources)


def build_record(
    *,
    run_id: str,
    case: EvaluationCase,
    result: Mapping[str, Any],
    router_mode: str,
    model_backend: str,
    search_backend: str,
    model_name: str = "mock",
    repeat_index: int = 1,
    prompt_version: str = "v1",
    input_price_per_million: float = 0.0,
    output_price_per_million: float = 0.0,
) -> EvaluationRecord:
    actual_route = list(result.get("route_history", []))
    expected = _unique(case.expected_agents)
    precision, recall = route_scores(expected, actual_route)
    metrics = [NodeMetric.model_validate(item) for item in result.get("metrics", [])]
    input_tokens = sum(metric.input_tokens for metric in metrics)
    output_tokens = sum(metric.output_tokens for metric in metrics)
    estimated_cost_usd = (
        input_tokens * input_price_per_million
        + output_tokens * output_price_per_million
    ) / 1_000_000
    missing_outputs = [name for name in case.required_outputs if not result.get(name)]
    source_count = len(result.get("sources", []))
    missing_source_outputs = [
        name
        for name in case.required_source_outputs
        if not _has_sources(result.get(name))
    ]
    repeated_agents = sorted(
        node for node, count in Counter(actual_route).items() if count > 1
    )
    forbidden_agents_hit = sorted(set(actual_route) & set(case.forbidden_agents))
    assertion_results = [
        evaluate_assertion(result, assertion) for assertion in case.assertions
    ]
    assertion_accuracy = (
        sum(item.passed for item in assertion_results) / len(assertion_results)
        if assertion_results
        else None
    )
    task_success = (
        result.get("status") == "completed"
        and not missing_outputs
        and not missing_source_outputs
        and (not case.requires_sources or source_count > 0)
        and all(item.passed for item in assertion_results)
    )
    return EvaluationRecord(
        run_id=run_id,
        case_id=case.id,
        repeat_index=repeat_index,
        router_mode=router_mode,
        model_backend=model_backend,
        model_name=model_name,
        prompt_version=prompt_version,
        search_backend=search_backend,
        status=str(result.get("status", "unknown")),
        expected_agents=expected,
        actual_route=actual_route,
        route_precision=round(precision, 4),
        route_recall=round(recall, 4),
        route_f1=round(_route_f1(precision, recall), 4),
        exact_route_match=Counter(expected) == Counter(actual_route),
        redundant_agents=sorted(set(actual_route) - set(expected)),
        missing_agents=sorted(set(expected) - set(actual_route)),
        forbidden_agents=case.forbidden_agents,
        task_success=task_success,
        missing_outputs=missing_outputs,
        missing_source_outputs=missing_source_outputs,
        repeated_agents=repeated_agents,
        forbidden_agents_hit=forbidden_agents_hit,
        assertion_results=assertion_results,
        assertion_accuracy=(round(assertion_accuracy, 4) if assertion_accuracy is not None else None),
        grounded_claim_rate=_grounded_claim_rate(result),
        source_count=source_count,
        error_count=len(result.get("errors", [])),
        total_latency_ms=int(result.get("elapsed_ms", 0)),
        token_usage=sum(metric.token_usage for metric in metrics),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model_calls=sum(metric.model_calls for metric in metrics),
        estimated_cost_usd=round(estimated_cost_usd, 8),
        node_metrics=metrics,
    )


def summarize(records: list[EvaluationRecord]) -> EvaluationSummary:
    if not records:
        raise ValueError("at least one evaluation record is required")
    count = len(records)
    assertion_records = [
        record.assertion_accuracy
        for record in records
        if record.assertion_accuracy is not None
    ]
    grounding_records = [
        record.grounded_claim_rate
        for record in records
        if record.grounded_claim_rate is not None
    ]
    latencies = [record.total_latency_ms for record in records]
    forbidden_records = [record for record in records if record.forbidden_agents]
    return EvaluationSummary(
        router_mode=records[0].router_mode,
        cases=count,
        task_success_rate=sum(record.task_success for record in records) / count,
        average_route_precision=sum(record.route_precision for record in records) / count,
        average_route_recall=sum(record.route_recall for record in records) / count,
        average_route_f1=sum(record.route_f1 for record in records) / count,
        exact_route_match_rate=sum(record.exact_route_match for record in records) / count,
        forbidden_agent_violation_rate=(
            sum(bool(record.forbidden_agents_hit) for record in forbidden_records)
            / len(forbidden_records)
            if forbidden_records
            else 0.0
        ),
        assertion_accuracy=(
            sum(assertion_records) / len(assertion_records) if assertion_records else None
        ),
        average_grounded_claim_rate=(
            sum(grounding_records) / len(grounding_records) if grounding_records else None
        ),
        error_free_rate=sum(record.error_count == 0 for record in records) / count,
        average_latency_ms=sum(record.total_latency_ms for record in records) / count,
        p50_latency_ms=_percentile(latencies, 0.50),
        p95_latency_ms=_percentile(latencies, 0.95),
        average_token_usage=sum(record.token_usage for record in records) / count,
        total_input_tokens=sum(record.input_tokens for record in records),
        total_output_tokens=sum(record.output_tokens for record in records),
        total_model_calls=sum(record.model_calls for record in records),
        total_estimated_cost_usd=round(
            sum(record.estimated_cost_usd for record in records), 8
        ),
    )
