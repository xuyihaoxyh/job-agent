from __future__ import annotations

import asyncio
import json

import pytest

from app.mcp.client import MCPSearchGateway, _json_from_tool_output


def test_parses_double_encoded_mcp_json_output():
    results = [
        {
            "title": "Example",
            "url": "https://example.com",
            "snippet": "content",
        }
    ]
    double_encoded = json.dumps(json.dumps(results))

    assert _json_from_tool_output(double_encoded) == results


def test_parses_mcp_text_content_blocks():
    blocks = [{"type": "text", "text": json.dumps([{"title": "Example"}])}]

    assert _json_from_tool_output(blocks) == [{"title": "Example"}]


def test_parses_one_json_object_per_mcp_text_block():
    blocks = [
        {"type": "text", "text": json.dumps({"title": "First"})},
        {"type": "text", "text": json.dumps({"title": "Second"})},
    ]

    assert _json_from_tool_output(blocks) == [
        {"title": "First"},
        {"title": "Second"},
    ]


@pytest.mark.asyncio
async def test_mcp_search_call_has_timeout(tmp_path):
    class SlowTool:
        name = "web_search"
        args = {"query": {}, "max_results": {}}

        async def ainvoke(self, arguments):
            await asyncio.sleep(0.05)
            return []

    gateway = MCPSearchGateway(
        config_path=tmp_path / "unused.json",
        timeout_seconds=0.01,
    )
    gateway._tool = SlowTool()

    with pytest.raises(TimeoutError):
        await gateway.search("query")
