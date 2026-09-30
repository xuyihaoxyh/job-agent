from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import median

from app.schemas.domain import SearchResult


_RANGE_PATTERN = re.compile(
    r"(?P<low>\d{1,3}(?:\.\d+)?)\s*(?:[kK千])?\s*[-–—~至]\s*"
    r"(?P<high>\d{1,3}(?:\.\d+)?)\s*[kK千]"
)
_SINGLE_MONTHLY_PATTERN = re.compile(
    r"(?:月薪|薪资|工资)[^\d]{0,8}(?P<value>\d{1,3}(?:\.\d+)?)\s*[kK千]"
    r"(?!\s*[-–—~至])",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class SalaryEstimate:
    minimum: int | None
    maximum: int | None
    sample_count: int
    ranges: tuple[tuple[int, int], ...]


def estimate_monthly_salary(results: list[SearchResult]) -> SalaryEstimate:
    ranges: set[tuple[int, int]] = set()
    for result in results:
        text = f"{result.title} {result.snippet}"
        for match in _RANGE_PATTERN.finditer(text):
            low = int(float(match.group("low")) * 1000)
            high = int(float(match.group("high")) * 1000)
            # Remove obvious OCR/unit errors and implausibly wide intervals.
            if 3_000 <= low <= high <= 200_000 and high / low <= 4:
                ranges.add((low, high))
        for match in _SINGLE_MONTHLY_PATTERN.finditer(text):
            value = int(float(match.group("value")) * 1000)
            if 3_000 <= value <= 200_000:
                ranges.add((value, value))
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
