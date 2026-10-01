from __future__ import annotations

import pytest

from app.schemas.domain import SearchResult, UserProfile


@pytest.fixture
def profile() -> UserProfile:
    return UserProfile(
        preferred_locations=["上海"],
        preferred_roles=["Java后端"],
        skills=["Java", "Spring Boot", "MySQL", "Redis", "Docker"],
        education="UNSW IT硕士",
        years_of_experience=3,
        experiences=["负责企业级Java服务开发"],
    )


@pytest.fixture
def search_results() -> list[SearchResult]:
    return [
        SearchResult(
            title="示例科技公司介绍",
            url="https://example.com/company",
            snippet="示例科技是一家企业软件服务商，主要服务金融和零售客户。",
        ),
        SearchResult(
            title="示例科技上海Java后端招聘 18K-25K",
            url="https://example.com/job-1",
            snippet="3-5年经验，月薪18K-25K。",
        ),
        SearchResult(
            title="Java工程师薪资 16K-22K",
            url="https://example.com/job-2",
            snippet="上海Java开发岗位月薪16K-22K。",
        ),
    ]
