from __future__ import annotations

import os

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("job-search")


@mcp.tool()
async def web_search(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Search the public web and return grounded results with title, URL, and snippet."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is required by the bundled search MCP server")

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "max_results": max(1, min(max_results, 10)),
                "search_depth": "basic",
                "include_answer": False,
            },
        )
        response.raise_for_status()
        payload = response.json()

    results = [
        {
            "title": item.get("title") or item.get("url", "Untitled"),
            "url": item.get("url", ""),
            "snippet": item.get("content", ""),
        }
        for item in payload.get("results", [])
        if item.get("url")
    ]
    return results


if __name__ == "__main__":
    mcp.run(transport="stdio")
