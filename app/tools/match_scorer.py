from __future__ import annotations

from app.schemas.domain import JDInfo, MatchResult, UserProfile


def _normalized(values: list[str]) -> dict[str, str]:
    return {value.casefold().strip(): value for value in values if value.strip()}


def score_match(jd: JDInfo, profile: UserProfile) -> MatchResult:
    required = _normalized(jd.required_skills)
    owned = _normalized(profile.skills)
    matched_keys = sorted(required.keys() & owned.keys())
    missing_keys = sorted(required.keys() - owned.keys())

    if required:
        skill_score = round(70 * len(matched_keys) / len(required))
    else:
        skill_score = 50

    experience_score = 20
    if jd.min_experience_years is not None:
        years = profile.years_of_experience or 0
        experience_score = round(min(years / jd.min_experience_years, 1) * 20)

    education_score = 10
    if jd.education_requirements and not profile.education:
        education_score = 0

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

    return MatchResult(
        score=score,
        recommendation=recommendation,
        advantages=advantages,
        gaps=gaps,
        matched_skills=[required[key] for key in matched_keys],
        missing_skills=[required[key] for key in missing_keys],
    )

