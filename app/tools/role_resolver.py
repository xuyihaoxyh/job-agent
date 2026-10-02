from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.schemas.domain import JDInfo


@dataclass(frozen=True, slots=True)
class SalarySearchRole:
    specific_name: str
    market_name: str
    source: Literal["user", "jd", "inferred"]


def resolve_salary_search_role(
    *,
    explicit_title: str | None,
    jd_info: JDInfo,
    jd_text: str,
) -> SalarySearchRole:
    """Resolve a search label without treating it as an extracted JD fact."""

    if explicit_title and explicit_title.strip():
        specific_name = explicit_title.strip()
        source: Literal["user", "jd", "inferred"] = "user"
    elif jd_info.role_name:
        specific_name = jd_info.role_name.strip()
        source = "jd"
    else:
        lowered = jd_text.casefold()
        has_ads = any(term in lowered for term in ("广告投放", "广告素材", "rta", "roas"))
        has_ai = any(term in lowered for term in ("ai", "agent", "rag", "llm", "大模型", "多模态"))
        has_backend = any(
            term in lowered
            for term in (
                "java",
                "golang",
                " go ",
                "后端",
                "分布式",
                "mysql",
                "redis",
                "消息队列",
                "api",
            )
        )
        if has_ads and has_ai:
            specific_name = "广告AI应用研发工程师"
        elif has_ai and has_backend:
            specific_name = "AI应用后端工程师"
        elif has_ai:
            specific_name = "AI应用研发工程师"
        elif has_backend:
            specific_name = "后端开发工程师"
        else:
            specific_name = "软件研发工程师"
        source = "inferred"

    context = f"{specific_name} {jd_text}".casefold()
    if any(term in context for term in ("ai", "agent", "rag", "llm", "大模型")):
        market_name = (
            "AI应用后端工程师"
            if any(
                term in context
                for term in ("java", "golang", " go ", "后端", "分布式", "mysql", "redis")
            )
            else "AI应用开发工程师"
        )
    elif any(term in context for term in ("java", "golang", " go ", "后端")):
        market_name = "后端开发工程师"
    else:
        market_name = specific_name

    return SalarySearchRole(
        specific_name=specific_name,
        market_name=market_name,
        source=source,
    )
