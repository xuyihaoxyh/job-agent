from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from pathlib import Path
from time import perf_counter

from app.evaluation.metrics import build_record, summarize
from app.evaluation.models import EvaluationCase
from app.graph.builder import build_graph
from app.graph.dependencies import GraphDependencies
from app.mcp.client import StaticSearchGateway
from app.schemas.domain import SearchResult, UserProfile
from app.services.model import DeterministicAnalysisModel


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


async def run(dataset: Path, output: Path) -> None:
    cases = load_cases(dataset)
    graph = build_graph(
        GraphDependencies(
            model=DeterministicAnalysisModel(),
            search=StaticSearchGateway(STATIC_RESULTS),
            profiles=DatasetProfiles(),
        )
    )
    run_id = str(uuid.uuid4())
    records = []
    for case in cases:
        started_at = perf_counter()
        result = await graph.ainvoke(case.request)
        result["elapsed_ms"] = max(0, round((perf_counter() - started_at) * 1000))
        result["route_history"] = [event.node for event in result.get("route_events", [])]
        records.append(
            build_record(
                run_id=run_id,
                case=case,
                result=result,
                router_mode="fixed",
                model_backend="mock",
                search_backend="static",
            )
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "\n".join(record.model_dump_json() for record in records) + "\n",
        encoding="utf-8",
    )
    print(summarize(records).model_dump_json(indent=2))
    print(f"records: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the deterministic router benchmark")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evaluations/cases.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluations/results/fixed.jsonl"),
    )
    args = parser.parse_args()
    asyncio.run(run(args.dataset, args.output))


if __name__ == "__main__":
    main()
