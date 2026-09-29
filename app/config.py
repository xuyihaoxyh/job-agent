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
    search_backend: str = "static"
    checkpoint_db: Path = PROJECT_ROOT / "data" / "checkpoints.db"
    app_db: Path = PROJECT_ROOT / "data" / "app.db"
    mcp_config_path: Path = PROJECT_ROOT / "app" / "mcp" / "servers.json"
    search_tool_name: str = "web_search"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            model_backend=os.getenv("MODEL_BACKEND", "mock").lower(),
            model_name=os.getenv("MODEL_NAME", "gpt-4.1-mini"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
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
        )

    def ensure_directories(self) -> None:
        self.checkpoint_db.parent.mkdir(parents=True, exist_ok=True)
        self.app_db.parent.mkdir(parents=True, exist_ok=True)
