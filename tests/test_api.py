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
        "user_id": "user-api",
        "jd_text": "招聘Java后端工程师，要求3年经验，熟悉Java、Spring Boot、MySQL和Redis，负责核心服务开发。",
        "company_name": "示例科技",
        "target_location": "上海",
        "user_profile": {
            "skills": ["Java", "Spring Boot", "MySQL", "Redis"],
            "education": "硕士",
            "years_of_experience": 3,
        },
    }

    with TestClient(app) as client:
        response = client.post("/api/v1/analyze", json=payload)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "completed"
        assert body["route_history"][0:2] == ["intake", "jd"]
        assert body["route_history"][-1] == "report"

        restored = client.get(f"/api/v1/threads/{body['thread_id']}")
        assert restored.status_code == 200
        assert restored.json()["status"] == "completed"

        # The profile was persisted separately, so it can be omitted next time.
        payload.pop("user_profile")
        second = client.post("/api/v1/analyze", json=payload)
        assert second.status_code == 200, second.text

