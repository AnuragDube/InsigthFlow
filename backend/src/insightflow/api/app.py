"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from insightflow.api import middleware
from insightflow.api.routers import health
from insightflow.core.logging import configure_logging
from insightflow.core.settings import Settings, get_settings
from insightflow.metadata.db import make_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    if settings.environment != "test":
        configure_logging()
    app = FastAPI(
        title="InsightFlow API",
        version="0.1.0",
        docs_url="/docs" if settings.environment == "dev" else None,
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url)
    middleware.install(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", middleware.CLIENT_HEADER, "X-Correlation-ID"],
        allow_credentials=False,
    )
    # Outermost: reject unexpected Host headers (defeats DNS rebinding against localhost).
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
    app.include_router(health.router)
    return app
