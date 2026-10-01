from __future__ import annotations

from time import perf_counter
from typing import Any

from app.schemas.domain import NodeMetric, RouteEvent


def timer() -> float:
    return perf_counter()


def token_usage(callback: Any) -> dict[str, int]:
    metadata = list(callback.usage_metadata.values())
    input_tokens = sum(int(item.get("input_tokens", 0)) for item in metadata)
    output_tokens = sum(int(item.get("output_tokens", 0)) for item in metadata)
    total_tokens = sum(int(item.get("total_tokens", 0)) for item in metadata)
    return {
        "token_usage": total_tokens or input_tokens + output_tokens,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def completed(
    node: str,
    started_at: float,
    *,
    token_usage: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    model_calls: int = 0,
) -> dict:
    return {
        "completed_agents": [node],
        "route_events": [RouteEvent(node=node, status="completed")],
        "metrics": [
            NodeMetric(
                node=node,
                latency_ms=max(0, round((perf_counter() - started_at) * 1000)),
                token_usage=token_usage,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model_calls=model_calls,
            )
        ],
        "step_count": 1,
    }
