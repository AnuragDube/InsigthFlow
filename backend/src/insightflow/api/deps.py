"""FastAPI dependencies: settings, engine, org context, request-size guard."""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.engine import Engine

from insightflow.core.context import OrgContext
from insightflow.core.settings import Settings


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_engine(request: Request) -> Engine:
    engine: Engine = request.app.state.engine
    return engine


def get_org_context(request: Request) -> OrgContext:
    """P0: every request acts for the local demo org (no authentication yet; see SECURITY.md).

    The org is never taken from request input. P1 replaces this with the authenticated principal.
    """
    ctx: OrgContext = request.app.state.demo_ctx
    return ctx
