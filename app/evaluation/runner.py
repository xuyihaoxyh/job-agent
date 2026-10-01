from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from dataclasses import replace
from pathlib import Path
from time import perf_counter

from app.config import Settings
from app.evaluation.metrics import build_record, summarize
from app.evaluation.models import EvaluationCase, EvaluationRecord, RouterMode
from app.graph.builder import build_graph
from app.graph.dependencies import GraphDependencies
from app.mcp.client import StaticSearchGateway
from app.schemas.domain import SearchResult, UserProfile
from app.services.model import build_analysis_model


class DatasetProfiles:
    async def get(self, user_id: str) -> UserProfile | None:
        return None


STATIC_RESULTS = [
    SearchResult(
        title="示例科技公司介绍",
        url="https://example.com/company",
        snippet="示例科技是一家企业软件服务商，主要服务金融和零售客户。",
    ),
    SearchResult(
        title="上海 Java 后端招聘 18K-25K",
        url="https://example.com/job-1",
        snippet="Java 后端岗位，3-5年经验，月薪18K-25K。",
    ),
    SearchResult(
        title="Java 工程师薪资 16K-22K",
        url="https://example.com/job-2",
        snippet="上海Java开发岗位月薪16K-22K。",
    ),
]


def load_cases(path: Path) -> list[EvaluationCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [EvaluationCase.model_validate(item) for item in payload]


def load_records(path: Path) -> list[EvaluationRecord]:
    if not path.exists():
        return []
    return [
        EvaluationRecord.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _route_history(result: dict) -> list[str]:
    return [
        event.node if hasattr(event, "node") else event["node"]
        for event in result.get("route_events", [])
    ]


def _build_graph(router_mode: RouterMode, settings: Settings):
    if router_mode != "fixed":
        raise ValueError(
            f"Router {router_mode!r} is not implemented yet; run the fixed baseline first"
        )
    return build_graph(
        GraphDependencies(
            model=build_analysis_model(settings),
            search=StaticSearchGateway(STATIC_RESULTS),
            profiles=DatasetProfiles(),
        )
    )


async def run(
    dataset: Path,
    output: Path,
    *,
    router_mode: RouterMode = "fixed",
    repeats: int = 1,
    model_backend: str = "mock",
    model_name: str = "gpt-4.1-mini",
    prompt_version: str = "v1",
    max_cost_usd: float = 2.0,
    input_price_per_million: float = 0.40,
    output_price_per_million: float = 1.60,
    resume: bool = False,
) -> list[EvaluationRecord]:
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    settings = replace(
        Settings.from_env(),
        model_backend=model_backend,
        model_name=model_name,
        search_backend="static",
    )
    graph = _build_graph(router_mode, settings)
    cases = load_cases(dataset)
    records = load_records(output) if resume else []
    completed_keys = {
        (record.case_id, record.repeat_index, record.router_mode) for record in records
    }
    spent = sum(record.estimated_cost_usd for record in records)
    run_id = str(uuid.uuid4())
    output.parent.mkdir(parents=True, exist_ok=True)
    if not resume:
        output.write_text("", encoding="utf-8")

    for repeat_index in range(1, repeats + 1):
        for case in cases:
            key = (case.id, repeat_index, router_mode)
            if key in completed_keys:
                continue
            if spent >= max_cost_usd:
                print(
                    f"budget stop: estimated ${spent:.4f} reached "
                    f"the ${max_cost_usd:.2f} limit"
                )
                return records

            graph_input = {**case.request, "router_mode": router_mode}
            started_at = perf_counter()
            result = await graph.ainvoke(graph_input)
            result["elapsed_ms"] = max(
                0, round((perf_counter() - started_at) * 1000)
            )
            result["route_history"] = _route_history(result)
            record = build_record(
                run_id=run_id,
                case=case,
                result=result,
                router_mode=router_mode,
                model_backend=model_backend,
                model_name=model_name,
                repeat_index=repeat_index,
                prompt_version=prompt_version,
                search_backend="static",
                input_price_per_million=input_price_per_million,
                output_price_per_million=output_price_per_million,
            )
            records.append(record)
            spent += record.estimated_cost_usd
            with output.open("a", encoding="utf-8") as stream:
                stream.write(record.model_dump_json() + "\n")

    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the router evaluation benchmark")
    parser.add_argument(
        "--dataset", type=Path, default=Path("evaluations/cases.json")
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluations/results/fixed.jsonl"),
    )
    parser.add_argument(
        "--router", choices=("fixed", "llm", "hybrid"), default="fixed"
    )
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--model-backend", choices=("mock", "openai"), default="mock")
    parser.add_argument("--model-name", default="gpt-4.1-mini")
    parser.add_argument("--prompt-version", default="v1")
    parser.add_argument("--max-cost-usd", type=float, default=2.0)
    parser.add_argument("--input-price-per-million", type=float, default=0.40)
    parser.add_argument("--output-price-per-million", type=float, default=1.60)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="required when --model-backend=openai to prevent accidental spending",
    )
    args = parser.parse_args()
    if args.model_backend == "openai" and not args.confirm_live:
        parser.error("--confirm-live is required when --model-backend=openai")

    records = asyncio.run(
        run(
            args.dataset,
            args.output,
            router_mode=args.router,
            repeats=args.repeats,
            model_backend=args.model_backend,
            model_name=args.model_name,
            prompt_version=args.prompt_version,
            max_cost_usd=args.max_cost_usd,
            input_price_per_million=args.input_price_per_million,
            output_price_per_million=args.output_price_per_million,
            resume=args.resume,
        )
    )
    if records:
        print(summarize(records).model_dump_json(indent=2))
    print(f"records: {args.output}")


if __name__ == "__main__":
    main()
