from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_client(tmp_path) -> TestClient:
    return TestClient(
        create_app(
            Settings(
                checkpoint_db=tmp_path / "checkpoints.db",
                app_db=tmp_path / "app.db",
                model_backend="mock",
                search_backend="static",
            )
        )
    )


def test_register_session_profile_update_and_logout(tmp_path):
    with make_client(tmp_path) as client:
        anonymous = client.get("/api/v1/auth/me")
        assert anonymous.status_code == 401

        registered = client.post(
            "/api/v1/auth/register",
            json={
                "username": "alice",
                "email": "Alice@example.com",
                "password": "correct-horse-battery",
            },
        )
        assert registered.status_code == 201, registered.text
        assert registered.json()["user"]["email"] == "alice@example.com"
        assert "job_agent_session" in registered.cookies

        current = client.get("/api/v1/auth/me")
        assert current.status_code == 200
        assert current.json()["user"]["username"] == "alice"

        updated = client.patch(
            "/api/v1/auth/me", json={"display_name": "Alice Chen"}
        )
        assert updated.status_code == 200
        assert updated.json()["user"]["display_name"] == "Alice Chen"

        empty_profile = client.get("/api/v1/profile")
        assert empty_profile.status_code == 200
        assert empty_profile.json()["profile"] is None

        profile_payload = {
            "preferred_locations": ["上海", "杭州"],
            "preferred_roles": ["Java后端"],
            "skills": ["Java", "Redis"],
            "education": "计算机硕士",
            "years_of_experience": 3,
            "experiences": ["负责交易系统开发"],
        }
        saved_profile = client.put("/api/v1/profile", json=profile_payload)
        assert saved_profile.status_code == 200
        assert client.get("/api/v1/profile").json()["profile"] == profile_payload

        duplicate = client.post(
            "/api/v1/auth/register",
            json={
                "username": "alice-2",
                "email": "alice@example.com",
                "password": "another-secure-pass",
            },
        )
        assert duplicate.status_code == 409

        logged_out = client.post("/api/v1/auth/logout")
        assert logged_out.status_code == 204
        assert client.get("/api/v1/auth/me").status_code == 401


def test_login_and_analysis_require_authentication(tmp_path):
    payload = {
        "jd_text": "招聘Java后端工程师，要求3年经验，熟悉Java、Spring Boot、MySQL和Redis，负责核心服务开发。",
        "company_name": "示例科技",
        "user_profile": {"skills": ["Java"], "years_of_experience": 3},
    }
    with make_client(tmp_path) as client:
        assert client.post("/api/v1/analyze", json=payload).status_code == 401
        client.post(
            "/api/v1/auth/register",
            json={
                "username": "bob",
                "email": "bob@example.com",
                "password": "bob-secure-password",
            },
        )
        client.post("/api/v1/auth/logout")

        bad_login = client.post(
            "/api/v1/auth/login", json={"login": "bob", "password": "wrong"}
        )
        assert bad_login.status_code == 401

        login = client.post(
            "/api/v1/auth/login",
            json={"login": "bob@example.com", "password": "bob-secure-password"},
        )
        assert login.status_code == 200
        analyzed = client.post("/api/v1/analyze", json=payload)
        assert analyzed.status_code == 200, analyzed.text

        custom_thread = client.post(
            "/api/v1/analyze", json={**payload, "thread_id": "someone-elses-thread"}
        )
        assert custom_thread.status_code == 422


def test_login_is_rate_limited_after_repeated_failures(tmp_path):
    with make_client(tmp_path) as client:
        client.post(
            "/api/v1/auth/register",
            json={
                "username": "limited",
                "email": "limited@example.com",
                "password": "correct-password",
            },
        )
        client.post("/api/v1/auth/logout")
        for _ in range(5):
            response = client.post(
                "/api/v1/auth/login",
                json={"login": "limited", "password": "wrong-password"},
            )
            assert response.status_code == 401

        blocked = client.post(
            "/api/v1/auth/login",
            json={"login": "limited", "password": "correct-password"},
        )
        assert blocked.status_code == 429


def test_thread_is_not_visible_to_another_user(tmp_path):
    payload = {
        "jd_text": "招聘Java后端工程师，要求3年经验，熟悉Java、Spring Boot、MySQL和Redis，负责核心服务开发。",
        "company_name": "示例科技",
        "user_profile": {"skills": ["Java"], "years_of_experience": 3},
    }
    with make_client(tmp_path) as client:
        client.post(
            "/api/v1/auth/register",
            json={"username": "owner", "email": "owner@example.com", "password": "owner-password"},
        )
        owner_profile = {
            "preferred_locations": ["上海"],
            "skills": ["Java"],
            "years_of_experience": 3,
        }
        assert client.put("/api/v1/profile", json=owner_profile).status_code == 200
        thread_id = client.post("/api/v1/analyze", json=payload).json()["thread_id"]
        client.post("/api/v1/auth/logout")
        client.post(
            "/api/v1/auth/register",
            json={"username": "other", "email": "other@example.com", "password": "other-password"},
        )
        assert client.get(f"/api/v1/threads/{thread_id}").status_code == 404
        assert client.get("/api/v1/profile").json()["profile"] is None
