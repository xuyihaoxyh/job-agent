from __future__ import annotations

import uuid
import logging
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder

from app.schemas.request import AnalyzeRequest
from app.schemas.response import AnalyzeResponse, ThreadStateResponse
from app.auth.dependencies import get_current_user
from app.schemas.auth import AuthUser


router = APIRouter(prefix="/api/v1", tags=["analysis"])
logger = logging.getLogger(__name__)


def _route_history(values: dict[str, Any]) -> list[str]:
    events = values.get("route_events", [])
    return [
        node
        for event in events
        if (node := event.node if hasattr(event, "node") else event.get("node"))
    ]


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    payload: AnalyzeRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
) -> AnalyzeResponse:
    request_started_at = perf_counter()
    graph = request.app.state.graph
    profiles = request.app.state.profiles
    # Thread IDs are server-generated. Accepting a caller-provided ID here would
    # allow a request to target another user's LangGraph checkpoint.
    thread_id = str(uuid.uuid4())

    if payload.user_profile is not None:
        await profiles.upsert(user.id, payload.user_profile)

    graph_input = payload.model_dump(exclude_none=True)
    graph_input["user_id"] = user.id
    config = {"configurable": {"thread_id": thread_id}}
    try:
        result = await graph.ainvoke(graph_input, config=config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Analysis failed for thread %s", thread_id)
        raise HTTPException(
            status_code=500,
            detail="分析执行失败，请稍后重试",
        ) from exc

    await request.app.state.auth.bind_thread(thread_id, user.id)

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
async def get_thread(
    thread_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
) -> ThreadStateResponse:
    if not await request.app.state.auth.owns_thread(thread_id, user.id):
        raise HTTPException(status_code=404, detail="Thread not found")
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
