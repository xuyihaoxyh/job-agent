from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_analyze_and_restore_thread(tmp_path):
    settings = Settings(
        checkpoint_db=tmp_path / "checkpoints.db",
        app_db=tmp_path / "app.db",
        model_backend="mock",
        search_backend="static",
    )
    app = create_app(settings)
    payload = {
        "jd_text": "招聘Java后端工程师，要求3年经验，熟悉Java、Spring Boot、MySQL和Redis，负责核心服务开发。",
        "company_name": "示例科技",
        "job_title": "Java后端工程师",
        "employment_type": "social",
        "target_location": "上海",
        "user_profile": {
            "skills": ["Java", "Spring Boot", "MySQL", "Redis"],
            "education": "硕士",
            "years_of_experience": 3,
        },
    }

    with TestClient(app) as client:
        web = client.get("/")
        assert web.status_code == 200
        assert "岗位分析工作台" in web.text
        assert "匹配度解释" in web.text
        assert "本次分析范围" in web.text
        assert 'id="userId"' not in web.text
        assert "/assets/app.js" in web.text
        script = client.get("/assets/app.js")
        styles = client.get("/assets/styles.css")
        assert script.status_code == 200
        assert styles.status_code == 200
        assert "/api/v1/profile" in script.text
        assert "/api/v1/analyses" in script.text

        registered = client.post(
            "/api/v1/auth/register",
            json={
                "username": "user-api",
                "email": "user-api@example.com",
                "password": "secure-pass-123",
            },
        )
        assert registered.status_code == 201, registered.text

        response = client.post("/api/v1/analyze", json=payload)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "completed"
        assert body["section_statuses"]["match"]["status"] == "completed"
        assert body["section_statuses"]["company"]["status"] == "insufficient"
        assert body["cost_summary"]["model_name"] == "gpt-4.1-mini"
        assert body["cost_summary"]["total_model_calls"] == 2
        assert body["cost_summary"]["estimated_cost_usd"] == 0
        assert body["cost_summary"]["billable"] is False
        assert body["route_history"][0:2] == ["intake", "jd"]
        assert body["route_history"][-1] == "report"
        assert body["step_count"] == 6
        assert body["elapsed_ms"] >= 0
        assert len(body["match_result"]["score_dimensions"]) == 3
        assert body["salary_info"]["role_name"] == "Java后端工程师"
        assert body["salary_info"]["role_source"] == "user"
        assert body["salary_info"]["employment_type"] == "social"
        assert {item["node"] for item in body["metrics"]} == {
            "intake",
            "jd",
            "company",
            "salary",
            "match",
            "report",
        }

        restored = client.get(f"/api/v1/threads/{body['thread_id']}")
        assert restored.status_code == 200
        assert restored.json()["status"] == "completed"

        history = client.get("/api/v1/analyses")
        assert history.status_code == 200
        assert history.json()["items"][0]["thread_id"] == body["thread_id"]
        assert history.json()["items"][0]["company_name"] == "示例科技"
        assert history.json()["items"][0]["match_score"] == body["match_result"]["score"]

        llm_payload = {
            **payload,
            "question": "这家公司主营业务和规模如何？",
            "router_mode": "llm",
        }
        llm_response = client.post("/api/v1/analyze", json=llm_payload)
        assert llm_response.status_code == 200, llm_response.text
        llm_body = llm_response.json()
        assert llm_body["router_mode"] == "llm"
        assert llm_body["route_history"] == ["intake", "jd", "company", "report"]
        assert llm_body["salary_info"] is None
        assert llm_body["match_result"] is None
        assert [item["next_agent"] for item in llm_body["router_decisions"]] == [
            "company",
            "report",
        ]
        assert "supervisor" in {item["node"] for item in llm_body["metrics"]}
        restored_llm = client.get(f"/api/v1/threads/{llm_body['thread_id']}")
        assert restored_llm.status_code == 200
        assert restored_llm.json()["values"]["router_mode"] == "llm"
        assert len(restored_llm.json()["values"]["router_decisions"]) == 2

        hybrid_payload = {
            **payload,
            "question": "这个岗位在上海的薪资待遇如何？",
            "router_mode": "hybrid",
        }
        hybrid_response = client.post("/api/v1/analyze", json=hybrid_payload)
        assert hybrid_response.status_code == 200, hybrid_response.text
        hybrid_body = hybrid_response.json()
        assert hybrid_body["router_mode"] == "hybrid"
        assert hybrid_body["route_history"] == ["intake", "jd", "salary", "report"]
        assert hybrid_body["router_decisions"] == []
        assert hybrid_body["analysis_plan"]["proposed_agents"] == ["salary"]
        assert hybrid_body["analysis_plan"]["final_agents"] == ["salary"]
        assert hybrid_body["analysis_plan"]["overridden"] is False
        assert hybrid_body["section_statuses"]["salary"]["status"] == "insufficient"
        assert hybrid_body["section_statuses"]["company"]["status"] == "not_requested"
        assert hybrid_body["section_statuses"]["match"]["status"] == "not_requested"

        fixed_company = client.post(
            "/api/v1/analyze",
            json={
                **payload,
                "question": "只分析公司公开信息",
                "analysis_targets": ["company"],
            },
        )
        assert fixed_company.status_code == 200, fixed_company.text
        fixed_company_body = fixed_company.json()
        assert fixed_company_body["analysis_targets"] == ["company"]
        assert fixed_company_body["route_history"] == ["intake", "jd", "company", "report"]
        assert fixed_company_body["salary_info"] is None
        assert fixed_company_body["match_result"] is None

        with client.stream("POST", "/api/v1/analyze/stream", json=payload) as streamed:
            assert streamed.status_code == 200
            content = "".join(streamed.iter_text())
        assert "event: accepted" in content
        assert "event: progress" in content
        assert '"node": "intake"' in content
        assert "event: result" in content

        # The profile was persisted separately, so it can be omitted next time.
        payload.pop("user_profile")
        second = client.post("/api/v1/analyze", json=payload)
        assert second.status_code == 200, second.text
        assert len(client.get("/api/v1/analyses").json()["items"]) == 6
