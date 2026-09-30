from __future__ import annotations

import json

from app.mcp.client import _json_from_tool_output


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
