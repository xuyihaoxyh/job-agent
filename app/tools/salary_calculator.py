from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import median

from app.schemas.domain import SearchResult
from app.tools.company_analyzer import result_mentions_company


_RANGE_PATTERN = re.compile(
    r"(?P<low>\d{1,3}(?:\.\d+)?)\s*(?:[kK千])?\s*[-–—~至]\s*"
    r"(?P<high>\d{1,3}(?:\.\d+)?)\s*[kK千]"
)
_SINGLE_MONTHLY_PATTERN = re.compile(
    r"(?:月薪|薪资|工资)[^\d]{0,8}(?P<value>\d{1,3}(?:\.\d+)?)\s*[kK千]"
    r"(?!\s*[-–—~至])",
    flags=re.IGNORECASE,
)
_YUAN_RANGE_PATTERN = re.compile(
    r"(?:[¥￥]\s*)?(?P<low>\d{4,6})\s*[-–—~至]\s*"
    r"(?P<high>\d{4,6})\s*(?:元)?(?:\s*/\s*月)?"
)


@dataclass(frozen=True, slots=True)
class SalaryEstimate:
    minimum: int | None
    maximum: int | None
    sample_count: int
    ranges: tuple[tuple[int, int], ...]


def _range_matches(text: str) -> list[tuple[int, int, int, int]]:
    matches: list[tuple[int, int, int, int]] = []
    for match in _RANGE_PATTERN.finditer(text):
        low = int(float(match.group("low")) * 1000)
        high = int(float(match.group("high")) * 1000)
        if 3_000 <= low <= high <= 200_000 and high / low <= 4:
            matches.append((low, high, match.start(), match.end()))
    for match in _YUAN_RANGE_PATTERN.finditer(text):
        low = int(match.group("low"))
        high = int(match.group("high"))
        if 3_000 <= low <= high <= 200_000 and high / low <= 4:
            matches.append((low, high, match.start(), match.end()))
    for match in _SINGLE_MONTHLY_PATTERN.finditer(text):
        value = int(float(match.group("value")) * 1000)
        if 3_000 <= value <= 200_000:
            matches.append((value, value, match.start(), match.end()))
    return matches


def result_has_salary_data(result: SearchResult) -> bool:
    text = f"{result.title} {result.snippet}"
    return bool(_range_matches(text))


def _role_terms(role_name: str) -> set[str]:
    lowered = role_name.casefold()
    terms = {
        token
        for token in re.findall(r"[a-z][a-z0-9+#.]{1,}|[\u4e00-\u9fff]{2,}", lowered)
        if token not in {"招聘", "岗位", "相关岗位", "工程师", "开发工程师"}
    }
    for marker in (
        "后端",
        "前端",
        "全栈",
        "算法",
        "数据",
        "测试",
        "运维",
        "产品",
        "架构",
        "开发",
    ):
        if marker in lowered:
            terms.add(marker)
    return terms


def _result_matches_role(result: SearchResult, role_name: str) -> bool:
    text = f"{result.title} {result.snippet}".casefold()
    role = role_name.casefold()
    groups: list[tuple[str, ...]] = []

    if any(term in role for term in ("广告", "投放", "rta", "roas")):
        groups.append(("广告", "投放", "营销", "用户增长", "rta", "roas"))
    if any(term in role for term in ("ai", "agent", "rag", "llm", "大模型")):
        groups.append(("ai", "agent", "rag", "llm", "大模型", "人工智能"))
    if "java" in role:
        groups.append(("java",))
    if "golang" in role or re.search(r"(?:^|\W)go(?:$|\W)", role):
        groups.append(("golang", "go语言"))
    if "后端" in role or "服务端" in role:
        groups.append(("后端", "服务端"))
    elif "应用" in role:
        groups.append(("应用", "业务落地", "场景落地"))
    elif "前端" in role:
        groups.append(("前端",))
    elif "算法" in role:
        groups.append(("算法", "模型"))
    elif "数据" in role:
        groups.append(("数据",))
    elif "测试" in role:
        groups.append(("测试", "质量"))
    elif "运维" in role:
        groups.append(("运维", "devops"))
    elif "产品" in role:
        groups.append(("产品",))

    if groups:
        return all(any(alias in text for alias in group) for group in groups)

    terms = _role_terms(role_name)
    return bool(terms) and any(term in text for term in terms)


def focus_salary_result_on_role(
    result: SearchResult, *, role_name: str
) -> SearchResult | None:
    """Keep salary ranges closest to the most specific role anchors.

    Search snippets often contain a matching job followed by company-wide or
    unrelated job ranges. The raw result remains available in search_attempts;
    this focused copy is used only for calculation.
    """

    text = f"{result.title} {result.snippet}".casefold()
    matches = _range_matches(text)
    if not matches:
        return None

    role = role_name.casefold()
    anchor_groups: list[tuple[str, ...]] = []
    if any(term in role for term in ("广告", "投放", "rta", "roas")):
        anchor_groups.append(("广告", "投放", "用户增长", "rta", "roas"))
    if any(term in role for term in ("ai", "agent", "rag", "llm", "大模型")):
        anchor_groups.append(("ai", "agent", "rag", "llm", "大模型", "人工智能"))
    if "java" in role:
        anchor_groups.append(("java",))
    if "后端" in role or "服务端" in role:
        anchor_groups.append(("后端", "服务端"))
    elif "应用" in role:
        anchor_groups.append(("应用", "业务落地", "场景落地"))

    anchors = [
        index
        for group in anchor_groups
        for alias in group
        for index in [text.find(alias)]
        if index >= 0
    ]
    if not anchors:
        return result

    ranked = sorted(
        matches,
        key=lambda item: min(abs(item[2] - anchor) for anchor in anchors),
    )
    best_distance = min(abs(ranked[0][2] - anchor) for anchor in anchors)
    selected = [
        item
        for item in ranked
        if min(abs(item[2] - anchor) for anchor in anchors) <= best_distance + 18
    ]
    focused_ranges = " ".join(
        f"{low / 1000:g}K-{high / 1000:g}K" for low, high, _, _ in selected
    )
    return SearchResult(title=role_name, url=result.url, snippet=focused_ranges)


def _result_matches_employment_type(result: SearchResult, employment_type: str) -> bool:
    title = result.title.casefold()
    text = f"{result.title} {result.snippet}".casefold()
    if employment_type == "social":
        return not any(term in title for term in ("校招", "校园招聘", "应届", "实习"))
    if employment_type == "campus":
        return any(term in text for term in ("校招", "校园招聘", "应届"))
    if employment_type == "intern":
        return "实习" in text
    return True


def result_is_company_salary_sample(
    result: SearchResult, *, company_name: str, role_name: str
) -> bool:
    return (
        result_has_salary_data(result)
        and result_mentions_company(result, company_name)
        and _result_matches_role(result, role_name)
    )


def filter_salary_results(
    results: list[SearchResult],
    *,
    role_name: str,
    location: str,
    employment_type: str = "social",
) -> list[SearchResult]:
    """Keep only salary samples grounded to the requested job context.

    Every sample must mention the role and target location. Company presence is
    tracked separately to distinguish company-specific evidence from the local
    market baseline. Merely containing a K-range is never sufficient evidence.
    """

    normalized_location = re.sub(r"\s+", "", location.casefold())
    nationwide = normalized_location in {"", "中国", "全国"}
    filtered: list[SearchResult] = []
    for result in results:
        if (
            not result_has_salary_data(result)
            or not _result_matches_role(result, role_name)
            or not _result_matches_employment_type(result, employment_type)
        ):
            continue
        text = re.sub(r"\s+", "", f"{result.title} {result.snippet}".casefold())
        location_specific = nationwide or normalized_location in text
        if location_specific:
            filtered.append(result)
    return filtered


def filter_valid_salary_results(
    results: list[SearchResult], *, max_ranges_per_result: int | None = None
) -> list[SearchResult]:
    """Apply final range validation per result.

    Company-specific search pages that expose many unrelated jobs can be
    limited with ``max_ranges_per_result``. Market aggregate pages deliberately
    keep all valid ranges because their scope is already labeled as market data.
    """

    valid: list[SearchResult] = []
    for result in results:
        sample_count = estimate_monthly_salary([result]).sample_count
        if sample_count == 0:
            continue
        if max_ranges_per_result is not None and sample_count > max_ranges_per_result:
            continue
        valid.append(result)
    return valid


def estimate_monthly_salary(results: list[SearchResult]) -> SalaryEstimate:
    ranges: set[tuple[int, int]] = set()
    for result in results:
        text = f"{result.title} {result.snippet}"
        for low, high, _, _ in _range_matches(text):
            ranges.add((low, high))
    ordered = tuple(sorted(ranges))
    if not ordered:
        return SalaryEstimate(None, None, 0, ())
    return SalaryEstimate(
        minimum=round(median(low for low, _ in ordered)),
        maximum=round(median(high for _, high in ordered)),
        sample_count=len(ordered),
        ranges=ordered,
    )


def extract_monthly_salary_range(results: list[SearchResult]) -> tuple[int | None, int | None]:
    estimate = estimate_monthly_salary(results)
    return estimate.minimum, estimate.maximum
