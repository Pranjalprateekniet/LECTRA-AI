"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from lectra_core.config import Settings, get_settings
from lectra_core.db.session import init_db
from lectra_core.logging import get_logger, setup_logging

from lectra_backend.api.v1 import api_v1_router

logger = get_logger("lectra.backend")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle handler."""
    settings = get_settings()
    setup_logging(settings)
    settings.ensure_directories()
    init_db(settings=settings)
    logger.info(
        "Lectra Backend started",
        extra={
            "environment": settings.environment,
            "backend_host": settings.backend_host,
            "backend_port": settings.backend_port,
        },
    )
    yield
    logger.info("Lectra Backend shutting down")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory for Lectra Backend."""
    active_settings = settings or get_settings()

    app = FastAPI(
        title="Revision RAG API",
        description="Searchable revision knowledge base built from YouTube playlists",
        version="0.1.0",
        lifespan=lifespan,
    )

    if settings is not None:
        from lectra_core.db.session import get_db

        from lectra_backend.dependencies import get_db_session

        def _override_get_settings():
            return active_settings

        def _override_get_db():
            yield from get_db(active_settings)

        app.dependency_overrides[get_settings] = _override_get_settings
        app.dependency_overrides[get_db_session] = _override_get_db

    # CORS configuration - restrict to local frontend by default
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            f"http://localhost:{active_settings.frontend_port}",
            f"http://127.0.0.1:{active_settings.frontend_port}",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount API routers
    app.include_router(api_v1_router, prefix="/api/v1")

    @app.get("/")
    def root():
        return {
            "name": "Revision RAG API",
            "version": "0.1.0",
            "docs": "/docs",
            "health": "/api/v1/health",
        }

    return app


app = create_app()


def start() -> None:
    """Run uvicorn server directly via CLI script."""
    settings = get_settings()
    uvicorn.run(
        "lectra_backend.main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    start()
