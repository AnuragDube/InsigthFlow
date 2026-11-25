"""FastAPI application factory."""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from insightflow.analytics.question_provider import QuestionProvider
from insightflow.api import middleware
from insightflow.api.background import run_in_background
from insightflow.api.body_limit import BodySizeLimitMiddleware
from insightflow.api.routers import analytics, datasets, health, runs
from insightflow.api.spa import SecurityHeadersMiddleware, mount_spa
from insightflow.core.logging import configure_logging
from insightflow.core.settings import Settings, get_settings
from insightflow.metadata.bootstrap import ensure_demo_org
from insightflow.metadata.db import make_engine, session_scope
from insightflow.metadata.migrate import upgrade_to_head
from insightflow.pipeline.service import recover_interrupted_runs

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    upgrade_to_head(settings.database_url)
    with session_scope(app.state.engine) as s:
        app.state.demo_ctx = ensure_demo_org(s, settings.demo_org_slug)
    # Single process: anything still 'running' was interrupted by a restart (ARCHITECTURE §3.1).
    for ctx, run_id in recover_interrupted_runs(app.state.engine):
        threading.Thread(
            target=run_in_background,
            args=(ctx, app.state.engine, settings, run_id),
            daemon=True,
        ).start()
    yield
    app.state.engine.dispose()


def create_app(
    settings: Settings | None = None, *, question_provider: QuestionProvider | None = None
) -> FastAPI:
    settings = settings or get_settings()
    if settings.environment != "test":
        configure_logging()
    app = FastAPI(
        lifespan=lifespan,
        title="InsightFlow API",
        version="0.1.0",
        docs_url="/docs" if settings.environment == "dev" else None,
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.question_provider = question_provider
    app.state.engine = make_engine(settings.database_url)
    middleware.install(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", middleware.CLIENT_HEADER, "X-Correlation-ID"],
        allow_credentials=False,
    )
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_bytes=settings.max_upload_mb * 1024 * 1024 + 64 * 1024,  # + multipart framing
        limit_mb=settings.max_upload_mb,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    # Outermost: reject unexpected Host headers (defeats DNS rebinding against localhost).
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
    app.include_router(health.router)
    app.include_router(datasets.router)
    app.include_router(runs.router)
    app.include_router(analytics.router)
    if settings.frontend_dist is not None:
        mount_spa(app, settings.frontend_dist)  # last: catch-all for client-side routes
    return app
