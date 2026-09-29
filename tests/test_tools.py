from app.schemas.domain import JDInfo, SearchResult, UserProfile
from app.tools.match_scorer import score_match
from app.tools.salary_calculator import extract_monthly_salary_range


def test_match_scorer_identifies_strengths_and_gaps():
    result = score_match(
        JDInfo(required_skills=["Java", "Redis", "Kubernetes"]),
        UserProfile(skills=["Java", "Redis"], years_of_experience=3),
    )
    assert result.matched_skills == ["Java", "Redis"]
    assert result.missing_skills == ["Kubernetes"]
    assert 0 <= result.score <= 100


def test_salary_range_extraction():
    result = extract_monthly_salary_range(
        [
            SearchResult(title="Java 15K-20K", url="https://a.example"),
            SearchResult(title="招聘", url="https://b.example", snippet="薪资17k-23k"),
        ]
    )
    assert result == (16000, 21500)

