from __future__ import annotations

from urllib.parse import urlparse

from app.schemas.domain import SearchResult, Source

RECRUITMENT_DOMAINS = {
    "zhaopin.com",
    "liepin.com",
    "zhipin.com",
    "jobui.com",
    "kanzhun.com",
    "glassdoor.com",
    "levels.fyi",
}
COMMUNITY_DOMAINS = {
    "reddit.com",
    "zhihu.com",
    "xiaohongshu.com",
    "nowcoder.com",
    "v2ex.com",
}
MEDIA_DOMAINS = {
    "36kr.com",
    "thepaper.cn",
    "caixin.com",
    "reuters.com",
    "bloomberg.com",
}


def _matches(host: str, domains: set[str]) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def classify_source(url: str, *, company_name: str | None = None) -> tuple[str, str]:
    host = urlparse(url).netloc.casefold().removeprefix("www.")
    if _matches(host, RECRUITMENT_DOMAINS):
        return "recruitment", "high"
    if _matches(host, COMMUNITY_DOMAINS):
        return "community", "low"
    if _matches(host, MEDIA_DOMAINS):
        return "media", "medium"
    if company_name and company_name.casefold() in host.replace("-", ""):
        return "official", "high"
    return "other", "medium"


def source_from_result(
    result: SearchResult,
    *,
    source_id: str,
    company_name: str | None = None,
    accepted: bool = True,
    reason: str | None = None,
    snippet_limit: int = 500,
) -> Source:
    source_type, quality = classify_source(result.url, company_name=company_name)
    snippet = " ".join(result.snippet.split())
    if len(snippet) > snippet_limit:
        snippet = snippet[:snippet_limit].rstrip() + "…"
    return Source(
        id=source_id,
        title=result.title,
        url=result.url,
        snippet=snippet,
        source_type=source_type,
        quality=quality,
        decision="accepted" if accepted else "rejected",
        decision_reason=reason
        or ("通过相关性与有效性校验" if accepted else "未通过相关性或有效性校验"),
    )
