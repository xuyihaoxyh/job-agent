from app.schemas.domain import JDInfo, SearchResult, Source, UserProfile
from app.tools.company_analyzer import build_company_info
from app.tools.match_scorer import score_match
from app.tools.salary_calculator import estimate_monthly_salary, extract_monthly_salary_range


def test_match_scorer_identifies_strengths_and_gaps():
    result = score_match(
        JDInfo(required_skills=["Java", "Redis", "Kubernetes"]),
        UserProfile(skills=["Java", "Redis"], years_of_experience=3),
    )
    assert result.matched_skills == ["Java", "Redis"]
    assert result.missing_skills == ["Kubernetes"]
    assert 0 <= result.score <= 100
    assert sum(item.score for item in result.score_dimensions) == result.score
    assert sum(item.max_score for item in result.score_dimensions) == 100


def test_salary_range_extraction():
    result = extract_monthly_salary_range(
        [
            SearchResult(title="Java 15K-20K", url="https://a.example"),
            SearchResult(title="招聘", url="https://b.example", snippet="薪资17k-23k"),
        ]
    )
    assert result == (16000, 21500)


def test_salary_estimate_filters_outliers_and_deduplicates():
    estimate = estimate_monthly_salary(
        [
            SearchResult(title="Java 15K-20K", url="https://a.example"),
            SearchResult(title="Java 15K-20K", url="https://b.example"),
            SearchResult(title="错误样本 0.8K-1.5K", url="https://c.example"),
            SearchResult(title="Java 18K-25K", url="https://d.example"),
            SearchResult(title="Java 20-30K", url="https://e.example"),
        ]
    )

    assert estimate.sample_count == 3
    assert estimate.minimum == 18000
    assert estimate.maximum == 25000


def test_company_analyzer_returns_compact_structured_info():
    results = [
        SearchResult(
            title="示例科技官网",
            url="https://example.com/about",
            snippet=(
                "示例科技是一家上市互联网公司，总部位于上海。"
                "公司提供云计算、人工智能和企业服务，员工人数约12,000人。"
                + "很长的历史信息。" * 80
            ),
        )
    ]
    sources = [
        Source(id="company-1", title=results[0].title, url=results[0].url)
    ]

    info = build_company_info(
        company_name="示例科技",
        jd_info=JDInfo(role_name="Java后端工程师"),
        results=results,
        sources=sources,
    )

    assert "上市公司" in (info.company_type or "")
    assert info.headquarters == "上海"
    assert {"云计算", "人工智能", "企业服务"} <= set(info.businesses)
    assert len(info.facts[0]) < 450
    assert "Java后端工程师" in (info.role_relevance or "")


def test_company_analyzer_does_not_use_subsidiary_headquarters():
    results = [
        SearchResult(
            title="示例公司",
            url="https://example.com",
            snippet=(
                "| 總部 | 中华人民共和国上海市浦东新区 |\n"
                "公司投资了另一家公司，该公司总部位于新加坡。"
            ),
        )
    ]
    info = build_company_info(
        company_name="示例公司",
        jd_info=JDInfo(role_name="后端工程师"),
        results=results,
        sources=[],
    )

    assert info.headquarters == "中华人民共和国上海市浦东新区"
