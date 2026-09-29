from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.api.analyze import router as analyze_router
from app.config import Settings
from app.graph.builder import build_graph
from app.graph.dependencies import GraphDependencies
from app.mcp.client import MCPSearchGateway, StaticSearchGateway
from app.memory.user_profile import SQLiteUserProfileRepository
from app.services.model import build_analysis_model


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        active_settings.ensure_directories()
        profiles = SQLiteUserProfileRepository(active_settings.app_db)
        await profiles.setup()
        model = build_analysis_model(active_settings)
        if active_settings.search_backend == "mcp":
            search = MCPSearchGateway(
                config_path=active_settings.mcp_config_path,
                tool_name=active_settings.search_tool_name,
            )
        elif active_settings.search_backend == "static":
            search = StaticSearchGateway()
        else:
            raise ValueError(
                f"Unsupported SEARCH_BACKEND: {active_settings.search_backend}"
            )

        async with AsyncSqliteSaver.from_conn_string(
            str(active_settings.checkpoint_db)
        ) as checkpointer:
            application.state.settings = active_settings
            application.state.profiles = profiles
            application.state.graph = build_graph(
                GraphDependencies(model=model, search=search, profiles=profiles),
                checkpointer=checkpointer,
            )
            yield

    application = FastAPI(title=active_settings.app_name, lifespan=lifespan)
    application.include_router(analyze_router)

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()

