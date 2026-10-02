from __future__ import annotations

import json
import logging
import uuid
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

from app.auth.dependencies import get_current_user
from app.schemas.auth import AuthUser
from app.schemas.domain import AnalysisSectionStatus
from app.schemas.request import AnalyzeRequest
from app.schemas.response import AnalyzeResponse, ThreadStateResponse
from app.services.costs import summarize_model_cost

router = APIRouter(prefix="/api/v1", tags=["analysis"])
logger = logging.getLogger(__name__)


def _route_history(values: dict[str, Any]) -> list[str]:
    events = values.get("route_events", [])
    return [
        node
        for event in events
        if (node := event.node if hasattr(event, "node") else event.get("node"))
    ]


def _section_statuses(result: dict[str, Any]) -> dict[str, AnalysisSectionStatus]:
    errors = [
        item.model_dump() if hasattr(item, "model_dump") else item
        for item in result.get("errors", [])
    ]
    errors_by_node = {item.get("node"): item for item in errors}

    def status_for(node: str, value: Any) -> AnalysisSectionStatus:
        error = errors_by_node.get(node)
        if value is None:
            return AnalysisSectionStatus(
                status="failed"
                if error and not error.get("recoverable", True)
                else "not_requested",
                message=(error.get("message") if error else "本次分析未请求该部分"),
            )
        if error:
            return AnalysisSectionStatus(status="degraded", message=error["message"])
        if node == "company" and not value.sources:
            return AnalysisSectionStatus(
                status="insufficient", message="未找到足够且可验证的公司公开证据"
            )
        if node == "salary" and value.data_scope == "insufficient":
            return AnalysisSectionStatus(
                status="insufficient", message="未识别出可靠的公司或市场薪资区间"
            )
        return AnalysisSectionStatus(status="completed", message="分析已完成")

    return {
        "company": status_for("company", result.get("company_info")),
        "salary": status_for("salary", result.get("salary_info")),
        "match": status_for("match", result.get("match_result")),
    }


async def _record_result(
    *, request: Request, user: AuthUser, payload: AnalyzeRequest, thread_id: str, result: dict
) -> None:
    await request.app.state.auth.bind_thread(thread_id, user.id)
    match_result = result.get("match_result")
    await request.app.state.history.record(
        thread_id=thread_id,
        user_id=user.id,
        company_name=result.get("company_name", payload.company_name),
        job_title=(result.get("jd_info").role_name if result.get("jd_info") else payload.job_title),
        status=result.get("status", "completed"),
        match_score=match_result.score if match_result else None,
        recommendation=match_result.recommendation if match_result else None,
    )


def _response_from_result(
    *,
    payload: AnalyzeRequest,
    thread_id: str,
    result: dict,
    elapsed_ms: int,
    settings: Any,
) -> AnalyzeResponse:
    return AnalyzeResponse(
        thread_id=thread_id,
        router_mode=payload.router_mode,
        analysis_targets=payload.analysis_targets,
        status=result.get("status", "completed"),
        match_result=result.get("match_result"),
        company_info=result.get("company_info"),
        salary_info=result.get("salary_info"),
        sources=result.get("sources", []),
        route_history=_route_history(result),
        metrics=result.get("metrics", []),
        router_decisions=result.get("router_decisions", []),
        analysis_plan=result.get("analysis_plan"),
        step_count=result.get("step_count", 0),
        elapsed_ms=elapsed_ms,
        final_report=result.get("final_report"),
        errors=jsonable_encoder(result.get("errors", [])),
        section_statuses=_section_statuses(result),
        cost_summary=summarize_model_cost(result.get("metrics", []), settings),
    )


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    payload: AnalyzeRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
) -> AnalyzeResponse:
    request_started_at = perf_counter()
    graph = request.app.state.graphs[payload.router_mode]
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

    await _record_result(
        request=request, user=user, payload=payload, thread_id=thread_id, result=result
    )
    return _response_from_result(
        payload=payload,
        thread_id=thread_id,
        result=result,
        elapsed_ms=max(0, round((perf_counter() - request_started_at) * 1000)),
        settings=request.app.state.settings,
    )


@router.post("/analyze/stream")
async def analyze_stream(
    payload: AnalyzeRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
) -> StreamingResponse:
    """Run the graph and stream real node completions as SSE events."""
    graph = request.app.state.graphs[payload.router_mode]
    thread_id = str(uuid.uuid4())
    if payload.user_profile is not None:
        await request.app.state.profiles.upsert(user.id, payload.user_profile)
    graph_input = payload.model_dump(exclude_none=True)
    graph_input["user_id"] = user.id
    config = {"configurable": {"thread_id": thread_id}}

    def event(name: str, data: dict[str, Any]) -> str:
        return f"event: {name}\ndata: {json.dumps(jsonable_encoder(data), ensure_ascii=False)}\n\n"

    async def generate():
        started_at = perf_counter()
        yield event("accepted", {"thread_id": thread_id, "router_mode": payload.router_mode})
        try:
            async for update in graph.astream(graph_input, config=config, stream_mode="updates"):
                for node, values in update.items():
                    if node.startswith("__"):
                        continue
                    route_events = (
                        values.get("route_events", []) if isinstance(values, dict) else []
                    )
                    status = "completed"
                    if route_events:
                        latest = route_events[-1]
                        status = (
                            latest.status
                            if hasattr(latest, "status")
                            else latest.get("status", status)
                        )
                    yield event("progress", {"node": node, "status": status})
            snapshot = await graph.aget_state(config)
            result = dict(snapshot.values)
            await _record_result(
                request=request,
                user=user,
                payload=payload,
                thread_id=thread_id,
                result=result,
            )
            response = _response_from_result(
                payload=payload,
                thread_id=thread_id,
                result=result,
                elapsed_ms=max(0, round((perf_counter() - started_at) * 1000)),
                settings=request.app.state.settings,
            )
            yield event("result", response.model_dump(mode="json"))
        except Exception:
            logger.exception("Streaming analysis failed for thread %s", thread_id)
            yield event("error", {"message": "分析执行失败，请稍后重试"})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
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
    mode = snapshot.values.get("router_mode", "fixed")
    graph = request.app.state.graphs.get(mode, graph)
    snapshot = await graph.aget_state(config)
    values = dict(snapshot.values)
    values["section_statuses"] = _section_statuses(values)
    values["cost_summary"] = summarize_model_cost(
        values.get("metrics", []), request.app.state.settings
    )
    return ThreadStateResponse(
        thread_id=thread_id,
        status=snapshot.values.get("status", "unknown"),
        values=jsonable_encoder(values),
        next_nodes=list(snapshot.next),
    )
