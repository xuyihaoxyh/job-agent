from __future__ import annotations

from time import perf_counter
from typing import Any

from app.schemas.domain import NodeMetric, RouteEvent


def timer() -> float:
    return perf_counter()


def token_usage(callback: Any) -> int:
    return sum(
        int(metadata.get("total_tokens", 0))
        for metadata in callback.usage_metadata.values()
    )


def completed(node: str, started_at: float, *, token_usage: int = 0) -> dict:
    return {
        "completed_agents": [node],
        "route_events": [RouteEvent(node=node, status="completed")],
        "metrics": [
            NodeMetric(
                node=node,
                latency_ms=max(0, round((perf_counter() - started_at) * 1000)),
                token_usage=token_usage,
            )
        ],
        "step_count": 1,
    }
