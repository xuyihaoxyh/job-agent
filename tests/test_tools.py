import pytest

from app.schemas.domain import JDInfo, SearchResult, Source, UserProfile
from app.tools.company_analyzer import (
    build_company_info,
    filter_company_results,
    result_mentions_company,
)
from app.tools.match_scorer import score_match
from app.tools.role_resolver import resolve_salary_search_role
from app.tools.salary_calculator import (
    estimate_monthly_salary,
    extract_monthly_salary_range,
    filter_salary_results,
    filter_valid_salary_results,
    focus_salary_result_on_role,
)
from app.services.model import DeterministicAnalysisModel


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


def test_match_scorer_understands_skill_aliases_and_education_levels():
    result = score_match(
        JDInfo(required_skills=["Go", "Kubernetes"], education_requirements=["本科"]),
        UserProfile(skills=["Golang", "K8s"], education="大专", years_of_experience=2),
    )

    assert result.matched_skills == ["Go", "Kubernetes"]
    assert result.score_dimensions[2].score == 0
    assert any("学历要求" in gap for gap in result.gaps)


def test_match_scorer_does_not_give_high_skill_score_without_extracted_skills():
    result = score_match(JDInfo(), UserProfile())

    assert result.score_dimensions[0].score == 35
    assert result.score == 65


@pytest.mark.asyncio
async def test_jd_experience_range_uses_lower_bound():
    info = await DeterministicAnalysisModel().extract_jd(
        "常规社招岗位，要求本科及以上学历，具有3–5 年研发经验，熟悉Java。"
    )

    assert info.min_experience_years == 3


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


def test_company_salary_rejects_multi_job_aggregate_page():
    specific = SearchResult(
        title="AI应用研发工程师 45K-65K",
        url="https://jobs.example/specific",
    )
    aggregate = SearchResult(
        title="公司全部职位",
        url="https://jobs.example/all",
        snippet=(
            "运维工程师25K-45K；大模型工程师40K-70K；"
            "经营分析30K-50K；财务负责人70K-100K。"
        ),
    )

    valid = filter_valid_salary_results(
        [specific, aggregate], max_ranges_per_result=3
    )

    assert valid == [specific]


def test_role_focused_salary_uses_nearest_yuan_range_not_company_average():
    result = SearchResult(
        title="米哈游招聘要求",
        url="https://jobs.example/mihoyo",
        snippet=(
            "米哈游最新招聘AI应用研发工程师-用户增长上海¥30000-60000 "
            "3-5年本科以上。米哈游整体薪酬区间6K-50K，最多岗位拿30-50K。"
        ),
    )

    focused = focus_salary_result_on_role(
        result,
        role_name="广告AI应用研发工程师",
    )
    assert focused is not None
    estimate = estimate_monthly_salary([focused])

    assert estimate.ranges == ((30000, 60000),)
    assert estimate.minimum == 30000
    assert estimate.maximum == 60000


def test_salary_search_results_must_match_role_and_company_or_location():
    relevant_market = SearchResult(
        title="上海 Java 后端工程师 18K-25K",
        url="https://jobs.example/java",
    )
    relevant_company = SearchResult(
        title="示例科技上海 Java 后端招聘 20K-30K",
        url="https://example.com/jobs",
    )
    unrelated_role = SearchResult(
        title="上海产品经理 30K-50K",
        url="https://jobs.example/product",
    )
    unrelated_location = SearchResult(
        title="北京 Java 后端工程师 25K-35K",
        url="https://jobs.example/beijing-java",
    )

    filtered = filter_salary_results(
        [relevant_market, relevant_company, unrelated_role, unrelated_location],
        role_name="Java后端工程师",
        location="上海",
    )

    assert filtered == [relevant_market, relevant_company]


def test_social_salary_search_rejects_campus_and_intern_results():
    social = SearchResult(
        title="上海AI应用后端工程师社招 25K-40K",
        url="https://jobs.example/social",
    )
    campus = SearchResult(
        title="上海AI应用后端工程师校招 20K-30K",
        url="https://jobs.example/campus",
    )
    intern = SearchResult(
        title="上海AI应用后端工程师实习 300元/天",
        url="https://jobs.example/intern",
        snippet="实习月薪6K-8K",
    )

    filtered = filter_salary_results(
        [social, campus, intern],
        role_name="AI应用后端工程师",
        location="上海",
        employment_type="social",
    )

    assert filtered == [social]


def test_complex_role_requires_all_key_dimensions():
    exact = SearchResult(
        title="上海AI应用研发工程师-用户增长 45K-65K",
        url="https://jobs.example/ad-ai",
        snippet="负责广告投放和用户增长场景的AI应用研发。",
    )
    adjacent = SearchResult(
        title="上海AI存储资深研发工程师 40K-70K",
        url="https://jobs.example/ai-storage",
        snippet="负责大模型存储平台研发。",
    )

    filtered = filter_salary_results(
        [exact, adjacent],
        role_name="广告AI应用研发工程师",
        location="上海",
        employment_type="social",
    )

    assert filtered == [exact]


def test_complex_ad_ai_jd_gets_searchable_inferred_role():
    jd_text = (
        "负责广告投放AI应用研发、Agent编排、RAG系统建设，"
        "精通Java或Go，熟悉MySQL、Redis和分布式系统。"
    )

    resolved = resolve_salary_search_role(
        explicit_title=None,
        jd_info=JDInfo(),
        jd_text=jd_text,
    )

    assert resolved.specific_name == "广告AI应用研发工程师"
    assert resolved.market_name == "AI应用后端工程师"
    assert resolved.source == "inferred"


def test_user_job_title_takes_priority_for_salary_search():
    resolved = resolve_salary_search_role(
        explicit_title="广告投放平台研发工程师",
        jd_info=JDInfo(role_name="Java后端工程师"),
        jd_text="负责广告投放AI应用研发，熟悉Java和分布式系统。",
    )

    assert resolved.specific_name == "广告投放平台研发工程师"
    assert resolved.source == "user"


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


@pytest.mark.parametrize(
    "statement",
    [
        "示例科技目前尚未上市，是一家互联网公司。",
        "示例科技已撤回上市申请。",
        "示例科技计划上市并持续发展企业服务业务。",
    ],
)
def test_company_analyzer_does_not_treat_listing_plans_as_listed(statement):
    result = SearchResult(
        title="示例科技公司资料",
        url="https://example.com/about",
        snippet=statement,
    )
    info = build_company_info(
        company_name="示例科技",
        jd_info=JDInfo(role_name="后端工程师"),
        results=[result],
        sources=[Source(id="company-1", title=result.title, url=result.url)],
    )

    assert "上市公司" not in (info.company_type or "")


def test_search_result_rejects_non_http_url():
    with pytest.raises(ValueError):
        SearchResult(title="unsafe", url="javascript:alert(1)")


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


def test_company_analyzer_rejects_unrelated_search_results():
    unrelated = SearchResult(
        title="腾讯云解决方案",
        url="https://cloud.tencent.com/solution",
        snippet="腾讯提供云计算、人工智能、社交、游戏和金融科技服务，是上市公司。",
    )
    source = Source(
        id="company-1",
        title=unrelated.title,
        url=unrelated.url,
        snippet=unrelated.snippet,
    )

    info = build_company_info(
        company_name="示例科技",
        jd_info=JDInfo(role_name="Java后端工程师"),
        results=[unrelated],
        sources=[source],
    )

    assert info.confidence == "low"
    assert info.businesses == []
    assert info.company_type is None
    assert info.sources == []
    assert "未找到能够明确对应" in info.summary
    assert "不代表公司不存在" in info.caveats[0]


def test_company_result_accepts_full_legal_name_alias():
    result = SearchResult(
        title="示例科技有限公司官方网站",
        url="https://example.com",
        snippet="示例科技有限公司提供企业软件服务。",
    )

    assert result_mentions_company(result, "示例科技有限公司")
    assert filter_company_results("示例科技有限公司", [result]) == [result]
