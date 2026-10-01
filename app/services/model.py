from __future__ import annotations

import json
import re

from langchain_openai import ChatOpenAI

from app.config import Settings
from app.schemas.domain import (
    CompanyInfo,
    JDInfo,
    MatchResult,
    SalaryInfo,
    UserProfile,
)
from app.services.protocols import AnalysisModel

KNOWN_SKILLS = [
    "Java",
    "Python",
    "Go",
    "JavaScript",
    "TypeScript",
    "Spring Boot",
    "MySQL",
    "PostgreSQL",
    "Redis",
    "Kafka",
    "RabbitMQ",
    "Docker",
    "Kubernetes",
    "AWS",
    "Azure",
    "GCP",
    "LangChain",
    "LangGraph",
]


class DeterministicAnalysisModel:
    """Offline implementation used by tests and local development without an API key."""

    async def extract_jd(self, jd_text: str) -> JDInfo:
        lowered = jd_text.lower()
        skills = [skill for skill in KNOWN_SKILLS if skill.lower() in lowered]
        years_range_match = re.search(
            r"(\d+(?:\.\d+)?)\s*[-–—~至]\s*(\d+(?:\.\d+)?)\s*年",
            jd_text,
        )
        years_match = re.search(r"(\d+(?:\.\d+)?)\s*年", jd_text)
        responsibilities = [
            part.strip(" -•\t")
            for part in re.split(r"[。；;\n]", jd_text)
            if len(part.strip()) >= 8
        ][:8]
        role_match = re.search(r"([A-Za-z]+|[\u4e00-\u9fff]+)(?:后端|开发|工程师|架构师)", jd_text)
        return JDInfo(
            role_name=role_match.group(0) if role_match else None,
            required_skills=skills,
            min_experience_years=(
                float(years_range_match.group(1))
                if years_range_match
                else float(years_match.group(1))
                if years_match
                else None
            ),
            education_requirements=[
                degree for degree in ["本科", "硕士", "博士"] if degree in jd_text
            ],
            responsibilities=responsibilities,
        )

    async def write_report(
        self,
        *,
        question: str,
        jd_info: JDInfo,
        company_info: CompanyInfo,
        salary_info: SalaryInfo,
        match_result: MatchResult,
        user_profile: UserProfile,
    ) -> str:
        source_lines = [
            f"- [{source.id}] [{source.title}]({source.url})"
            for source in company_info.sources + salary_info.sources
        ]
        salary_range = (
            f"{salary_info.minimum:,}–{salary_info.maximum:,} "
            f"{salary_info.currency}/{salary_info.period}"
            if salary_info.minimum is not None and salary_info.maximum is not None
            else "未找到足够可靠的数据"
        )
        salary_scope = {
            "company": "目标公司相关岗位",
            "market": "同地区同岗位市场参考（降级结果）",
            "insufficient": "信息不足",
        }[salary_info.data_scope]
        role_source = {
            "user": "用户填写",
            "jd": "JD 提取",
            "inferred": "系统推断",
            None: "未知",
        }[salary_info.role_source]
        employment_type = {
            "social": "常规社招",
            "campus": "校园招聘",
            "intern": "实习招聘",
        }[salary_info.employment_type]
        salary_search_lines = [
            f"- 搜索过程：{attempt.scope} 检索返回 {attempt.raw_result_count} 条，"
            f"采纳 {attempt.accepted_result_count} 条"
            for attempt in salary_info.search_attempts
        ]
        company_details = [
            company_info.summary,
            *(
                [f"- 企业性质：{company_info.company_type}"]
                if company_info.company_type
                else []
            ),
            *(
                [f"- 总部：{company_info.headquarters}"]
                if company_info.headquarters
                else []
            ),
            *(
                [f"- 公开业务：{'、'.join(company_info.businesses)}"]
                if company_info.businesses
                else []
            ),
            *(
                [f"- 规模：{company_info.employee_scale}"]
                if company_info.employee_scale
                else []
            ),
            *([f"- 岗位关联：{company_info.role_relevance}"] if company_info.role_relevance else []),
            *[f"- 注意：{item}" for item in company_info.caveats],
        ]
        score_lines = [
            f"- {dimension.label}：{dimension.score}/{dimension.max_score}（{dimension.detail}）"
            for dimension in match_result.score_dimensions
        ]
        return "\n".join(
            [
                "# 岗位分析报告",
                "",
                f"**分析目标：** {question}",
                f"**匹配度：** {match_result.score}/100（{match_result.recommendation}）",
                "",
                "## 岗位匹配",
                *score_lines,
                f"- 优势：{'；'.join(match_result.advantages) or '暂无明显优势'}",
                f"- 缺口：{'；'.join(match_result.gaps) or '未发现关键缺口'}",
                f"- 说明：{match_result.scoring_note}",
                "",
                "## 公司信息",
                *company_details,
                "",
                "## 薪资信息",
                f"{salary_range}。{salary_info.summary}",
                f"- 数据范围：{salary_scope}",
                f"- 检索岗位：{salary_info.role_name or '未知'}（{role_source}）",
                f"- 招聘类型：{employment_type}",
                f"- 有效薪资区间：{salary_info.sample_count} 个",
                f"- 计算方法：{salary_info.methodology}",
                *salary_search_lines,
                *[f"- 注意：{item}" for item in salary_info.caveats],
                "",
                "## 来源",
                *(source_lines or ["- 未获取到外部来源，相关结论可信度较低。"]),
            ]
        )


class OpenAIAnalysisModel:
    def __init__(
        self,
        *,
        model_name: str,
        api_key: str,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
    ) -> None:
        self._model = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            temperature=0,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )
        self._jd_model = self._model.with_structured_output(JDInfo)

    async def extract_jd(self, jd_text: str) -> JDInfo:
        result = await self._jd_model.ainvoke(
            [
                (
                    "system",
                    "从招聘JD中抽取结构化要求。只记录原文明确表达的内容，不要猜测。",
                ),
                ("human", jd_text),
            ]
        )
        return JDInfo.model_validate(result)

    async def write_report(
        self,
        *,
        question: str,
        jd_info: JDInfo,
        company_info: CompanyInfo,
        salary_info: SalaryInfo,
        match_result: MatchResult,
        user_profile: UserProfile,
    ) -> str:
        payload = {
            "question": question,
            "jd_info": jd_info.model_dump(mode="json"),
            "company_info": company_info.model_dump(mode="json"),
            # Raw search attempts are diagnostic evidence for the UI. They may
            # contain rejected results and must never be summarized as facts.
            "salary_info": salary_info.model_dump(
                mode="json", exclude={"search_attempts"}
            ),
            "match_result": match_result.model_dump(mode="json"),
            "user_profile": user_profile.model_dump(mode="json"),
        }
        response = await self._model.ainvoke(
            [
                (
                    "system",
                    "你是求职分析报告编辑。只能汇总输入JSON中的事实，不得添加新事实。"
                    "所有公司和薪资事实必须保留对应来源ID；缺失信息明确写未知。"
                    "当公司或薪资confidence为low且sources为空时，只能表述为无法验证或信息不足，"
                    "不得推断公司存在、不存在、企业性质、业务、规模或薪资。"
                    "搜索不到信息不等于目标不存在。",
                ),
                ("human", json.dumps(payload, ensure_ascii=False)),
            ]
        )
        return str(response.content)


def build_analysis_model(settings: Settings) -> AnalysisModel:
    if settings.model_backend == "mock":
        return DeterministicAnalysisModel()
    if settings.model_backend == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("MODEL_BACKEND=openai requires OPENAI_API_KEY")
        return OpenAIAnalysisModel(
            model_name=settings.model_name,
            api_key=settings.openai_api_key,
            timeout_seconds=settings.model_timeout_seconds,
            max_retries=settings.model_max_retries,
        )
    raise ValueError(f"Unsupported MODEL_BACKEND: {settings.model_backend}")
