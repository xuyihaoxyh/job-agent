from __future__ import annotations

import re
from urllib.parse import urlparse

from app.schemas.domain import CompanyInfo, JDInfo, SearchResult, Source


_BUSINESS_KEYWORDS = {
    "云计算": ("云计算", "云服务", "公有云", "混合云"),
    "人工智能": ("人工智能", "AI", "大模型"),
    "企业服务": ("企业服务", "产业互联网", "数字化"),
    "社交平台": ("社交", "即时通讯", "社交网络"),
    "游戏": ("游戏", "网络游戏"),
    "金融科技": ("金融科技", "支付", "财付通"),
    "电商": ("电子商务", "电商", "零售商业"),
    "内容娱乐": ("数字媒体", "娱乐", "视频", "文学"),
    "物流": ("物流", "供应链"),
}


def _clean_text(value: str, *, limit: int = 420) -> str:
    text = re.sub(r"\[\.\.\.\]|\.{3,}", "", value)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"\b(?:播报|编辑|编辑维基数据)\b", "", text)
    text = text.replace("|", " ")
    text = re.sub(r"\s+", " ", text).strip(" -：;")
    if len(text) <= limit:
        return text
    shortened = text[:limit]
    boundary = max(shortened.rfind("。"), shortened.rfind("；"))
    return (shortened[: boundary + 1] if boundary >= limit // 2 else shortened) + "…"


def _first_match(patterns: list[str], text: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _clean_text(match.group(1), limit=50)
    return None


def _source_quality(result: SearchResult) -> int:
    title = result.title.casefold()
    host = urlparse(result.url).netloc.casefold()
    score = 0
    if any(word in title for word in ("官方", "财报", "业绩", "年报", "公告")):
        score += 4
    if host.endswith((".com", ".cn", ".com.cn")):
        score += 1
    if "wikipedia.org" in host or "baidu.com" in host:
        score += 1
    if any(word in host for word in ("blog", "csdn", "zhihu")):
        score -= 2
    return score


def _headquarters(company_name: str, results: list[SearchResult]) -> str | None:
    # Prefer infobox/table values because generic snippets may mention the
    # headquarters of subsidiaries or companies being invested in.
    table_patterns = [
        r"(?:总部|總部)\s*\|\s*([^|\n]{2,80})",
        r"(?:总部|總部)\s*[:：]\s*([^。；|\n]{2,80})",
    ]
    own_sentence_patterns = [
        rf"{re.escape(company_name)}[^。；\n]{{0,35}}(?:总部|總部)(?:位于|位於|设在|設在|所在地为)?\s*([^。；\n]{{2,60}})",
    ]
    for patterns in (table_patterns, own_sentence_patterns):
        for result in results:
            value = _first_match(patterns, result.snippet)
            if value:
                return value
    return None


def build_company_info(
    *,
    company_name: str,
    jd_info: JDInfo,
    results: list[SearchResult],
    sources: list[Source],
) -> CompanyInfo:
    ranked = sorted(results, key=_source_quality, reverse=True)
    combined = " ".join(result.snippet for result in ranked if result.snippet)
    facts = [_clean_text(result.snippet) for result in ranked if result.snippet][:3]

    company_types: list[str] = []
    if "上市" in combined:
        company_types.append("上市公司")
    if "民营" in combined:
        company_types.append("民营企业")
    if any(word in combined for word in ("互联网", "科技公司", "技术公司")):
        company_types.append("科技/互联网企业")

    businesses = [
        name
        for name, keywords in _BUSINESS_KEYWORDS.items()
        if any(keyword.casefold() in combined.casefold() for keyword in keywords)
    ][:6]
    headquarters = _headquarters(company_name, ranked)
    employee_scale = _first_match(
        [
            r"(?:员工|雇员)(?:总数|人数|数)?(?:为|有|达到|约)?\s*([\d,.]+\s*万?人)",
            r"([\d,.]+\s*万?名?(?:员工|雇员))",
        ],
        combined,
    )

    summary = facts[0] if facts else "未找到足够可靠的公开公司信息。"
    if businesses:
        summary = f"{company_name}公开业务主要涉及{'、'.join(businesses)}。"
        if headquarters:
            summary += f"公开资料显示总部位于{headquarters}。"

    role_name = jd_info.role_name or "当前"
    role_relevance = (
        f"当前分析岗位为{role_name}；公司公开业务包括{'、'.join(businesses)}。"
        "具体所属部门和业务线仍需向招聘方确认。"
        if businesses
        else f"当前分析岗位为{role_name}，但公开搜索结果不足以判断具体业务归属。"
    )
    has_high_quality_source = any(_source_quality(result) >= 4 for result in results)
    confidence = (
        "high"
        if len(sources) >= 3 and has_high_quality_source
        else "medium"
        if len(sources) >= 2
        else "low"
    )
    return CompanyInfo(
        company_name=company_name,
        summary=summary,
        company_type="、".join(dict.fromkeys(company_types)) or None,
        headquarters=headquarters,
        businesses=businesses,
        employee_scale=employee_scale,
        role_relevance=role_relevance,
        caveats=["员工规模和财务数据可能对应不同披露期，请以最新官方材料为准。"],
        facts=facts,
        confidence=confidence,
        sources=sources,
    )
