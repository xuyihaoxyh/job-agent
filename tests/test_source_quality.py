from app.schemas.domain import SearchResult
from app.tools.source_quality import source_from_result


def test_source_quality_marks_recruitment_result_and_rejection_reason():
    result = SearchResult(
        title="示例岗位薪资",
        url="https://www.zhipin.com/job/example",
        snippet="上海 Java 工程师 20K-30K",
    )

    source = source_from_result(
        result,
        source_id="salary-search-1",
        accepted=False,
        reason="岗位不一致，未用于薪资计算",
    )

    assert source.source_type == "recruitment"
    assert source.quality == "high"
    assert source.decision == "rejected"
    assert source.decision_reason == "岗位不一致，未用于薪资计算"
    assert source.published_at is None
    assert source.freshness == "unknown"
