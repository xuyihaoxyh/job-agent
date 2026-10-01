from __future__ import annotations

import json
import os
import sys
import asyncio
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.schemas.domain import SearchResult
from app.services.protocols import SearchGateway
from pydantic import ValidationError


def _json_from_tool_output(value: Any) -> Any:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            # Some MCP adapters JSON-encode a tool's string return value again.
            # Recursing here supports both a normal JSON payload and that
            # double-encoded representation.
            return _json_from_tool_output(parsed) if parsed != value else parsed
        except json.JSONDecodeError:
            return value
    if isinstance(value, dict):
        if "content" in value:
            return _json_from_tool_output(value["content"])
        return value
    if isinstance(value, list):
        text_parts: list[str] = []
        for item in value:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(str(item.get("text", "")))
            elif hasattr(item, "text"):
                text_parts.append(str(item.text))
            elif isinstance(item, str):
                text_parts.append(item)
        if text_parts:
            parsed_parts = [_json_from_tool_output(part) for part in text_parts]
            if all(isinstance(part, dict) for part in parsed_parts):
                return parsed_parts
            if all(isinstance(part, list) for part in parsed_parts):
                return [item for part in parsed_parts for item in part]
            if len(parsed_parts) == 1:
                return parsed_parts[0]
            return _json_from_tool_output("".join(text_parts))
    return value


class MCPSearchGateway(SearchGateway):
    def __init__(
        self,
        *,
        config_path: Path,
        tool_name: str = "web_search",
        timeout_seconds: float = 35.0,
    ) -> None:
        self._config_path = config_path
        self._tool_name = tool_name
        self._timeout_seconds = timeout_seconds
        self._tool: BaseTool | None = None
        self._tool_lock = asyncio.Lock()

    async def _get_tool(self) -> BaseTool:
        if self._tool is not None:
            return self._tool
        async with self._tool_lock:
            if self._tool is not None:
                return self._tool
            config = json.loads(self._config_path.read_text(encoding="utf-8"))
            for server in config.values():
                if server.get("command") in {"python", "python3"}:
                    server["command"] = sys.executable
                # The MCP stdio client starts a separate child process and only
                # forwards a restricted environment by default. Inject the search
                # credential at runtime instead of storing it in servers.json.
                tavily_api_key = os.getenv("TAVILY_API_KEY")
                if tavily_api_key:
                    server.setdefault("env", {}).setdefault(
                        "TAVILY_API_KEY", tavily_api_key
                    )
            client = MultiServerMCPClient(config)
            tools = await asyncio.wait_for(
                client.get_tools(), timeout=self._timeout_seconds
            )
            for tool in tools:
                if tool.name == self._tool_name or tool.name.endswith(self._tool_name):
                    self._tool = tool
                    return tool
            available = ", ".join(tool.name for tool in tools)
            raise RuntimeError(
                f"MCP tool {self._tool_name!r} was not found. Available tools: {available}"
            )

    @staticmethod
    def _arguments(tool: BaseTool, query: str, max_results: int) -> dict[str, Any]:
        # LangChain's generic invocation schema accepts str/dict/ToolCall, while
        # `tool.args` exposes the actual MCP input schema.
        properties = tool.args
        args: dict[str, Any] = {}
        for candidate in ("query", "search_query", "q"):
            if candidate in properties:
                args[candidate] = query
                break
        else:
            raise RuntimeError(f"Search tool {tool.name!r} has no supported query argument")
        if "max_results" in properties:
            args["max_results"] = max_results
        elif "limit" in properties:
            args["limit"] = max_results
        return args

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        tool = await self._get_tool()
        output = await asyncio.wait_for(
            tool.ainvoke(self._arguments(tool, query, max_results)),
            timeout=self._timeout_seconds,
        )
        parsed = _json_from_tool_output(output)
        if isinstance(parsed, dict):
            parsed = parsed.get("results", [])
        if not isinstance(parsed, list):
            raise RuntimeError(f"Unexpected MCP search output: {type(parsed).__name__}")
        results: list[SearchResult] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            try:
                results.append(SearchResult.model_validate(item))
            except ValidationError:
                continue
        return results


class StaticSearchGateway(SearchGateway):
    """Offline search implementation for tests and MODEL_BACKEND=mock demos."""

    def __init__(self, results: list[SearchResult] | None = None) -> None:
        self._results = results or []

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        return self._results[:max_results]
