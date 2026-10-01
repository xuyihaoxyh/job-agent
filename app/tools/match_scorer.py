from __future__ import annotations

import re

from app.schemas.domain import JDInfo, MatchResult, MatchScoreDimension, UserProfile


_SKILL_ALIASES = {
    "golang": "go",
    "go语言": "go",
    "springboot": "spring boot",
    "k8s": "kubernetes",
    "postgres": "postgresql",
    "js": "javascript",
    "ts": "typescript",
}


def _normalized(values: list[str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for value in values:
        key = re.sub(r"[\s._-]+", " ", value.casefold()).strip()
        compact = key.replace(" ", "")
        canonical = _SKILL_ALIASES.get(key, _SKILL_ALIASES.get(compact, key))
        if canonical:
            normalized[canonical] = value
    return normalized


def _education_rank(value: str | None) -> int | None:
    if not value:
        return None
    for label, rank in (("博士", 4), ("硕士", 3), ("本科", 2), ("大专", 1), ("专科", 1)):
        if label in value:
            return rank
    return None


def score_match(jd: JDInfo, profile: UserProfile) -> MatchResult:
    required = _normalized(jd.required_skills)
    owned = _normalized(profile.skills)
    matched_keys = sorted(required.keys() & owned.keys())
    missing_keys = sorted(required.keys() - owned.keys())

    if required:
        skill_score = round(70 * len(matched_keys) / len(required))
    else:
        # Missing extraction evidence is uncertainty, not a positive match.
        skill_score = 35

    experience_score = 20
    if jd.min_experience_years is not None:
        years = profile.years_of_experience or 0
        experience_score = round(min(years / jd.min_experience_years, 1) * 20)

    education_score = 10
    education_gap: str | None = None
    if jd.education_requirements:
        required_ranks = [
            rank
            for value in jd.education_requirements
            if (rank := _education_rank(value)) is not None
        ]
        required_rank = min(required_ranks) if required_ranks else None
        profile_rank = _education_rank(profile.education)
        if profile_rank is None:
            education_score = 0
            education_gap = "学历信息缺失或无法识别，需确认是否满足JD要求"
        elif required_rank is not None and profile_rank < required_rank:
            education_score = 0
            education_gap = (
                f"学历要求为{'/'.join(jd.education_requirements)}，"
                f"当前资料为{profile.education}"
            )

    score = max(0, min(100, skill_score + experience_score + education_score))
    if score >= 80:
        recommendation = "建议投递"
    elif score >= 60:
        recommendation = "可以投递，但需要补强材料"
    else:
        recommendation = "谨慎投递"

    advantages = [f"匹配技能：{required[key]}" for key in matched_keys]
    gaps = [f"缺少或未体现：{required[key]}" for key in missing_keys]
    if jd.min_experience_years and (profile.years_of_experience or 0) < jd.min_experience_years:
        gaps.append(
            f"JD要求至少{jd.min_experience_years:g}年经验，当前资料为"
            f"{profile.years_of_experience or 0:g}年"
        )
    if education_gap:
        gaps.append(education_gap)

    return MatchResult(
        score=score,
        recommendation=recommendation,
        advantages=advantages,
        gaps=gaps,
        matched_skills=[required[key] for key in matched_keys],
        missing_skills=[required[key] for key in missing_keys],
        score_dimensions=[
            MatchScoreDimension(
                key="skills",
                label="技能匹配",
                score=skill_score,
                max_score=70,
                detail=(
                    f"匹配 {len(matched_keys)}/{len(required)} 项明确技能"
                    if required
                    else "JD 未识别出明确技能，按不确定信息给予中性分"
                ),
            ),
            MatchScoreDimension(
                key="experience",
                label="经验匹配",
                score=experience_score,
                max_score=20,
                detail=(
                    f"个人资料 {profile.years_of_experience or 0:g} 年 / "
                    f"JD 要求 {jd.min_experience_years:g} 年"
                    if jd.min_experience_years is not None
                    else "JD 未明确最低工作年限"
                ),
            ),
            MatchScoreDimension(
                key="education",
                label="学历信息",
                score=education_score,
                max_score=10,
                detail=(
                    f"个人资料：{profile.education or '未提供'}；JD："
                    f"{'/'.join(jd.education_requirements)}"
                    if jd.education_requirements
                    else "JD 未明确学历要求"
                ),
            ),
        ],
    )
