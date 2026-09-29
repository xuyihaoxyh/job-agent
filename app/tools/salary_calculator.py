from __future__ import annotations

import re

from app.schemas.domain import SearchResult


_RANGE_PATTERN = re.compile(
    r"(?P<low>\d{1,3}(?:\.\d+)?)\s*[kK千]\s*[-–—~至]\s*"
    r"(?P<high>\d{1,3}(?:\.\d+)?)\s*[kK千]"
)


def extract_monthly_salary_range(results: list[SearchResult]) -> tuple[int | None, int | None]:
    ranges: list[tuple[int, int]] = []
    for result in results:
        text = f"{result.title} {result.snippet}"
        for match in _RANGE_PATTERN.finditer(text):
            low = int(float(match.group("low")) * 1000)
            high = int(float(match.group("high")) * 1000)
            if 1_000 <= low <= high <= 500_000:
                ranges.append((low, high))
    if not ranges:
        return None, None
    return (
        round(sum(low for low, _ in ranges) / len(ranges)),
        round(sum(high for _, high in ranges) / len(ranges)),
    )

