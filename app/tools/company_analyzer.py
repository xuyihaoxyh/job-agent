from __future__ import annotations

import re
from urllib.parse import urlparse

from app.schemas.domain import CompanyFact, CompanyInfo, JDInfo, SearchResult, Source

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

_LEGAL_SUFFIXES = (
    "股份有限公司",
    "有限责任公司",
    "集团有限公司",
    "有限公司",
    "股份公司",
    "集团",
    "公司",
)


def _normalize_entity_name(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.casefold())


def _company_name_variants(company_name: str) -> set[str]:
    normalized = _normalize_entity_name(company_name)
    variants = {normalized} if normalized else set()
    for suffix in _LEGAL_SUFFIXES:
        normalized_suffix = _normalize_entity_name(suffix)
        if normalized.endswith(normalized_suffix):
            base = normalized[: -len(normalized_suffix)]
            if len(base) >= 2:
                variants.add(base)
            break
    return variants


def result_mentions_company(result: SearchResult, company_name: str) -> bool:
    """Return whether a result explicitly names the requested company.

    Search ranking is semantic, so appearing in a result set does not prove the
    page is about the target entity. Exact normalized name/alias presence is the
    minimum evidence gate before any company fact may be extracted.
    """

    haystack = _normalize_entity_name(f"{result.title} {result.snippet}")
    return any(variant in haystack for variant in _company_name_variants(company_name))


def filter_company_results(
    company_name: str, results: list[SearchResult]
) -> list[SearchResult]:
    return [result for result in results if result_mentions_company(result, company_name)]


def _grounded_sentences(company_name: str, result: SearchResult) -> list[str]:
    variants = _company_name_variants(company_name)
    sentences = [
        part.strip()
        for part in re.split(r"(?<=[。！？!?；;])|\n+", result.snippet)
        if part.strip()
    ]
    grounded: list[str] = []
    previous_was_grounded = False
    for sentence in sentences:
        normalized = _normalize_entity_name(sentence)
        if any(marker in sentence for marker in ("竞争对手", "同行相比", "对比", "区别于")):
            previous_was_grounded = False
            continue
        explicitly_grounded = any(variant in normalized for variant in variants)
        pronoun_continuation = previous_was_grounded and bool(
            re.match(r"^(?:公司|该公司|其|集团|企业)", sentence)
        )
        if explicitly_grounded or pronoun_continuation:
            grounded.append(sentence)
            previous_was_grounded = True
        else:
            previous_was_grounded = False

    # Search engines sometimes omit the entity from the first snippet sentence
    # because it is already present in the title. Only that first sentence gets
    # this conservative title-context fallback.
    title = _normalize_entity_name(result.title)
    title_matches = any(variant in title for variant in variants)
    if not grounded and title_matches and sentences:
        first = sentences[0]
        if not any(marker in first for marker in ("竞争对手", "同行相比", "对比", "区别于")):
            grounded.append(first)
    return grounded


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


def _is_publicly_listed(text: str) -> bool:
    """Require affirmative listing evidence and reject common negative contexts."""

    negative_patterns = (
        r"(?:未|尚未|没有|并未|不是|非)上市",
        r"上市(?:申请)?(?:已)?(?:撤回|终止|中止|失败|未通过|被否)",
        r"(?:撤回|终止|中止)上市(?:申请)?",
        r"(?:计划|拟|寻求|准备|考虑|冲刺|试图)上市",
    )
    cleaned = text
    for pattern in negative_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    positive_patterns = (
        r"(?:是|为|属于|成为)[^。；\n]{0,12}上市[^。；\n]{0,8}公司",
        r"(?:于|在)[^。；\n]{0,20}(?:证券交易所|上交所|深交所|港交所|纳斯达克|纽交所)[^。；\n]{0,12}上市",
        r"股票代码\s*[:：]?\s*[0-9A-Z.]{4,}",
        r"(?:A股|港股|美股)上市",
    )
    return any(re.search(pattern, cleaned, flags=re.IGNORECASE) for pattern in positive_patterns)


def _headquarters_from_text(company_name: str, text: str) -> str | None:
    return _first_match(
        [
            r"(?:总部|總部)\s*\|\s*([^|\n]{2,80})",
            r"(?:总部|總部)\s*[:：]\s*([^。；|\n]{2,80})",
            rf"{re.escape(company_name)}[^。；\n]{{0,35}}(?:总部|總部)(?:位于|位於|设在|設在|所在地为)?\s*([^。；\n]{{2,60}})",
            r"(?:总部|總部)(?:位于|位於|设在|設在|所在地为)\s*([^。；\n]{2,60})",
        ],
        text,
    )


def build_company_info(
    *,
    company_name: str,
    jd_info: JDInfo,
    results: list[SearchResult],
    sources: list[Source],
) -> CompanyInfo:
    # Defense in depth: callers should filter first so sources stay aligned,
    # while the analyzer also refuses unrelated results when used directly.
    relevant_results = filter_company_results(company_name, results)
    grounded_results = [
        (result, " ".join(_grounded_sentences(company_name, result)))
        for result in relevant_results
    ]
    grounded_results = [(result, text) for result, text in grounded_results if text]
    relevant_urls = {result.url for result, _ in grounded_results}
    relevant_sources = [source for source in sources if source.url in relevant_urls]
    ranked = sorted(grounded_results, key=lambda item: _source_quality(item[0]), reverse=True)
    if not ranked:
        return CompanyInfo(
            company_name=company_name,
            summary=f"未找到能够明确对应“{company_name}”的可靠公开信息。",
            role_relevance="公司主体尚未得到公开来源验证，无法判断岗位所属业务。",
            caveats=[
                "搜索不到相关信息不代表公司不存在，可能是名称不完整、同名或公开信息较少。",
                "建议补充公司全称、官网、招聘页面或所在城市后重新分析。",
            ],
            confidence="low",
            sources=[],
        )
    combined = " ".join(text for _, text in ranked)
    facts = [_clean_text(text) for _, text in ranked][:3]
    source_by_url = {source.url: source for source in relevant_sources}
    evidence = [
        CompanyFact(
            claim=_clean_text(text),
            source_ids=[source_by_url[result.url].id] if result.url in source_by_url else [],
        )
        for result, text in ranked[:3]
    ]

    company_types: list[str] = []
    listed_evidence = any(_is_publicly_listed(text) for _, text in ranked)
    nonlisted_evidence = any(
        re.search(r"(?:未|尚未|没有|并未|不是|非)上市|(?:撤回|终止|中止)上市", text)
        for _, text in ranked
    )
    listing_conflict = listed_evidence and nonlisted_evidence
    if listed_evidence and not listing_conflict:
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
    headquarters_values = {
        value
        for _, text in ranked
        if (value := _headquarters_from_text(company_name, text))
    }
    headquarters = next(iter(headquarters_values)) if len(headquarters_values) == 1 else None
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
    has_high_quality_source = any(_source_quality(result) >= 4 for result, _ in ranked)
    confidence = (
        "high"
        if len(relevant_sources) >= 3 and has_high_quality_source
        else "medium"
        if len(relevant_sources) >= 2
        else "low"
    )
    caveats = ["员工规模和财务数据可能对应不同披露期，请以最新官方材料为准。"]
    if listing_conflict:
        caveats.append("公开来源对上市状态表述冲突，暂不判断是否为上市公司。")
    if len(headquarters_values) > 1:
        caveats.append("公开来源中的总部信息不一致，暂不展示总部结论。")
    if len(relevant_sources) < 2:
        caveats.append("当前仅有单一相关来源，尚不足以完成交叉验证。")
    return CompanyInfo(
        company_name=company_name,
        summary=summary,
        company_type="、".join(dict.fromkeys(company_types)) or None,
        headquarters=headquarters,
        businesses=businesses,
        employee_scale=employee_scale,
        role_relevance=role_relevance,
        caveats=caveats,
        facts=facts,
        evidence=evidence,
        confidence=confidence,
        sources=relevant_sources,
    )
