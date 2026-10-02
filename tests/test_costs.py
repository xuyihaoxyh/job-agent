from app.config import Settings
from app.schemas.domain import NodeMetric
from app.services.costs import summarize_model_cost


def test_gpt_41_mini_cost_summary_uses_input_and_output_rates():
    summary = summarize_model_cost(
        [
            NodeMetric(
                node="jd",
                latency_ms=10,
                input_tokens=1000,
                output_tokens=500,
                token_usage=1500,
                model_calls=1,
            ),
            NodeMetric(
                node="report",
                latency_ms=20,
                input_tokens=2000,
                output_tokens=1000,
                token_usage=3000,
                model_calls=1,
            ),
        ],
        Settings(model_backend="openai", model_name="gpt-4.1-mini"),
    )

    assert summary.total_input_tokens == 3000
    assert summary.total_output_tokens == 1500
    assert summary.total_tokens == 4500
    assert summary.total_model_calls == 2
    assert summary.estimated_cost_usd == 0.0036
    assert summary.pricing_source == "official_default"
    assert summary.billable is True


def test_unknown_model_without_prices_is_not_estimated():
    summary = summarize_model_cost(
        [NodeMetric(node="jd", latency_ms=1, token_usage=10, model_calls=1)],
        Settings(model_backend="openai", model_name="unknown-model"),
    )

    assert summary.estimated_cost_usd is None
    assert summary.pricing_source == "unavailable"


def test_mock_model_is_explicitly_non_billable():
    summary = summarize_model_cost(
        [NodeMetric(node="report", latency_ms=1, model_calls=1)],
        Settings(model_backend="mock", model_name="gpt-4.1-mini"),
    )

    assert summary.total_model_calls == 1
    assert summary.estimated_cost_usd == 0
    assert summary.billable is False
