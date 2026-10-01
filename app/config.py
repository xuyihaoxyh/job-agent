from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "Job Analysis Agent"
    model_backend: str = "mock"
    model_name: str = "gpt-4.1-mini"
    openai_api_key: str | None = None
    model_timeout_seconds: float = 60.0
    model_max_retries: int = 2
    search_backend: str = "static"
    checkpoint_db: Path = PROJECT_ROOT / "data" / "checkpoints.db"
    app_db: Path = PROJECT_ROOT / "data" / "app.db"
    mcp_config_path: Path = PROJECT_ROOT / "app" / "mcp" / "servers.json"
    search_tool_name: str = "web_search"
    search_timeout_seconds: float = 35.0
    session_cookie_name: str = "job_agent_session"
    session_ttl_hours: int = 168
    session_cookie_secure: bool = False
    login_max_attempts: int = 5
    login_window_seconds: int = 300

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            model_backend=os.getenv("MODEL_BACKEND", "mock").lower(),
            model_name=os.getenv("MODEL_NAME", "gpt-4.1-mini"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            model_timeout_seconds=float(os.getenv("MODEL_TIMEOUT_SECONDS", "60")),
            model_max_retries=int(os.getenv("MODEL_MAX_RETRIES", "2")),
            search_backend=os.getenv("SEARCH_BACKEND", "static").lower(),
            checkpoint_db=Path(
                os.getenv("CHECKPOINT_DB", PROJECT_ROOT / "data" / "checkpoints.db")
            ),
            app_db=Path(os.getenv("APP_DB", PROJECT_ROOT / "data" / "app.db")),
            mcp_config_path=Path(
                os.getenv(
                    "MCP_CONFIG_PATH", PROJECT_ROOT / "app" / "mcp" / "servers.json"
                )
            ),
            search_tool_name=os.getenv("MCP_SEARCH_TOOL", "web_search"),
            search_timeout_seconds=float(os.getenv("SEARCH_TIMEOUT_SECONDS", "35")),
            session_cookie_name=os.getenv("SESSION_COOKIE_NAME", "job_agent_session"),
            session_ttl_hours=int(os.getenv("SESSION_TTL_HOURS", "168")),
            session_cookie_secure=os.getenv("SESSION_COOKIE_SECURE", "false").lower()
            in {"1", "true", "yes"},
            login_max_attempts=int(os.getenv("LOGIN_MAX_ATTEMPTS", "5")),
            login_window_seconds=int(os.getenv("LOGIN_WINDOW_SECONDS", "300")),
        )

    def ensure_directories(self) -> None:
        self.checkpoint_db.parent.mkdir(parents=True, exist_ok=True)
        self.app_db.parent.mkdir(parents=True, exist_ok=True)
