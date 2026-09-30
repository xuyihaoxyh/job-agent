from __future__ import annotations

import uuid
from time import perf_counter
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder

from app.schemas.request import AnalyzeRequest
from app.schemas.response import AnalyzeResponse, ThreadStateResponse


router = APIRouter(prefix="/api/v1", tags=["analysis"])


def _route_history(values: dict[str, Any]) -> list[str]:
    events = values.get("route_events", [])
    result: list[str] = []
    for event in events:
        node = event.node if hasattr(event, "node") else event.get("node")
        if node and node not in result:
            result.append(node)
    return result


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(payload: AnalyzeRequest, request: Request) -> AnalyzeResponse:
    request_started_at = perf_counter()
    graph = request.app.state.graph
    profiles = request.app.state.profiles
    thread_id = payload.thread_id or str(uuid.uuid4())

    if payload.user_profile is not None:
        await profiles.upsert(payload.user_id, payload.user_profile)

    graph_input = payload.model_dump(exclude={"thread_id"}, exclude_none=True)
    config = {"configurable": {"thread_id": thread_id}}
    try:
        result = await graph.ainvoke(graph_input, config=config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}") from exc

    return AnalyzeResponse(
        thread_id=thread_id,
        status=result.get("status", "completed"),
        match_result=result.get("match_result"),
        company_info=result.get("company_info"),
        salary_info=result.get("salary_info"),
        sources=result.get("sources", []),
        route_history=_route_history(result),
        metrics=result.get("metrics", []),
        step_count=result.get("step_count", 0),
        elapsed_ms=max(0, round((perf_counter() - request_started_at) * 1000)),
        final_report=result.get("final_report"),
        errors=jsonable_encoder(result.get("errors", [])),
    )


@router.get("/threads/{thread_id}", response_model=ThreadStateResponse)
async def get_thread(thread_id: str, request: Request) -> ThreadStateResponse:
    graph = request.app.state.graph
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = await graph.aget_state(config)
    if not snapshot.values:
        raise HTTPException(status_code=404, detail="Thread not found")
    return ThreadStateResponse(
        thread_id=thread_id,
        status=snapshot.values.get("status", "unknown"),
        values=jsonable_encoder(snapshot.values),
        next_nodes=list(snapshot.next),
    )
