from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from app.config import Settings
from app.schemas.domain import CostSummary, NodeCost, NodeMetric

# Standard text-token prices in USD per 1M tokens. Environment overrides take
# precedence so pricing can be updated without a code deployment.
KNOWN_PRICES: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-4.1-mini": (Decimal("0.40"), Decimal("1.60")),
    "gpt-4.1-mini-2025-04-14": (Decimal("0.40"), Decimal("1.60")),
}


def _pricing(settings: Settings) -> tuple[Decimal | None, Decimal | None, str]:
    if (
        settings.model_input_price_per_1m is not None
        and settings.model_output_price_per_1m is not None
    ):
        return (
            Decimal(str(settings.model_input_price_per_1m)),
            Decimal(str(settings.model_output_price_per_1m)),
            "environment",
        )
    known = KNOWN_PRICES.get(settings.model_name)
    if known:
        return known[0], known[1], "official_default"
    return None, None, "unavailable"


def _cost(
    *,
    input_tokens: int,
    output_tokens: int,
    input_price: Decimal | None,
    output_price: Decimal | None,
    billable: bool,
) -> float | None:
    if input_price is None or output_price is None:
        return None
    if not billable:
        return 0.0
    amount = (
        Decimal(input_tokens) * input_price
        + Decimal(output_tokens) * output_price
    ) / Decimal(1_000_000)
    return float(amount.quantize(Decimal("0.00000001")))


def summarize_model_cost(
    metrics: Iterable[NodeMetric | dict], settings: Settings
) -> CostSummary:
    validated = [NodeMetric.model_validate(metric) for metric in metrics]
    input_price, output_price, pricing_source = _pricing(settings)
    billable = settings.model_backend == "openai"
    nodes = [
        NodeCost(
            node=metric.node,
            input_tokens=metric.input_tokens,
            output_tokens=metric.output_tokens,
            total_tokens=metric.token_usage,
            model_calls=metric.model_calls,
            estimated_cost_usd=_cost(
                input_tokens=metric.input_tokens,
                output_tokens=metric.output_tokens,
                input_price=input_price,
                output_price=output_price,
                billable=billable,
            ),
        )
        for metric in validated
        if metric.model_calls or metric.token_usage
    ]
    total_input = sum(item.input_tokens for item in nodes)
    total_output = sum(item.output_tokens for item in nodes)
    total_tokens = sum(item.total_tokens for item in nodes)
    total_calls = sum(item.model_calls for item in nodes)
    estimated_cost = _cost(
        input_tokens=total_input,
        output_tokens=total_output,
        input_price=input_price,
        output_price=output_price,
        billable=billable,
    )
    if not billable:
        note = "当前使用 Mock 模型，不产生 OpenAI API 费用。"
    elif estimated_cost is None:
        note = "当前模型未配置单价，无法估算；不包含 MCP/Tavily 搜索费用。"
    else:
        note = "按文本 Token 标准单价估算；不包含缓存折扣、MCP/Tavily 搜索费用及税费。"
    return CostSummary(
        model_name=settings.model_name,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_tokens=total_tokens,
        total_model_calls=total_calls,
        estimated_cost_usd=estimated_cost,
        input_price_per_1m=float(input_price) if input_price is not None else None,
        output_price_per_1m=float(output_price) if output_price is not None else None,
        pricing_source=pricing_source,
        billable=billable,
        note=note,
        nodes=nodes,
    )
