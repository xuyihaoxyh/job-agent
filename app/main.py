from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.api.analyze import router as analyze_router
from app.api.auth import router as auth_router
from app.api.history import router as history_router
from app.api.profile import router as profile_router
from app.auth.rate_limit import LoginRateLimiter
from app.auth.repository import SQLiteAuthRepository
from app.config import Settings
from app.graph.builder import build_graph
from app.graph.dependencies import GraphDependencies
from app.mcp.client import MCPSearchGateway, StaticSearchGateway
from app.memory.analysis_history import SQLiteAnalysisHistoryRepository
from app.memory.user_profile import SQLiteUserProfileRepository
from app.services.model import build_analysis_model

WEB_DIR = Path(__file__).resolve().parent / "web"
CHECKPOINT_TYPES = [
    ("app.schemas.domain", name)
    for name in (
        "CompanyFact",
        "CompanyInfo",
        "JDInfo",
        "MatchResult",
        "MatchScoreDimension",
        "NodeError",
        "NodeMetric",
        "RouteEvent",
        "SalaryInfo",
        "SalarySearchAttempt",
        "Source",
        "UserProfile",
    )
]


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        active_settings.ensure_directories()
        profiles = SQLiteUserProfileRepository(active_settings.app_db)
        history = SQLiteAnalysisHistoryRepository(active_settings.app_db)
        auth = SQLiteAuthRepository(
            active_settings.app_db, session_ttl_hours=active_settings.session_ttl_hours
        )
        login_limiter = LoginRateLimiter(
            max_attempts=active_settings.login_max_attempts,
            window_seconds=active_settings.login_window_seconds,
        )
        await profiles.setup()
        await history.setup()
        await auth.setup()
        model = build_analysis_model(active_settings)
        if active_settings.search_backend == "mcp":
            search = MCPSearchGateway(
                config_path=active_settings.mcp_config_path,
                tool_name=active_settings.search_tool_name,
                timeout_seconds=active_settings.search_timeout_seconds,
            )
        elif active_settings.search_backend == "static":
            search = StaticSearchGateway()
        else:
            raise ValueError(
                f"Unsupported SEARCH_BACKEND: {active_settings.search_backend}"
            )

        serializer = JsonPlusSerializer(allowed_msgpack_modules=CHECKPOINT_TYPES)
        async with aiosqlite.connect(active_settings.checkpoint_db) as checkpoint_connection:
            checkpointer = AsyncSqliteSaver(checkpoint_connection, serde=serializer)
            application.state.settings = active_settings
            application.state.profiles = profiles
            application.state.history = history
            application.state.auth = auth
            application.state.login_limiter = login_limiter
            application.state.graph = build_graph(
                GraphDependencies(model=model, search=search, profiles=profiles),
                checkpointer=checkpointer,
            )
            yield

    application = FastAPI(title=active_settings.app_name, lifespan=lifespan)
    application.include_router(analyze_router)
    application.include_router(auth_router)
    application.include_router(profile_router)
    application.include_router(history_router)
    application.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")

    @application.get("/", include_in_schema=False)
    async def web_app() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
