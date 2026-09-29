from __future__ import annotations

from time import perf_counter

from app.schemas.domain import NodeMetric, RouteEvent


def timer() -> float:
    return perf_counter()


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

