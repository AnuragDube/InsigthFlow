"""FastAPI dependencies: settings, engine, org context, request-size guard."""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.engine import Engine

from insightflow.core.context import OrgContext
from insightflow.core.errors import AppError, PayloadTooLarge
from insightflow.core.settings import Settings


class LengthRequired(AppError):
    status, type_slug, title = 411, "length-required", "Length required"


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


def limit_upload_size(request: Request) -> None:
    """Reject oversized bodies *before* multipart parsing spools them to disk."""
    settings: Settings = request.app.state.settings
    limit = settings.max_upload_mb * 1024 * 1024 + 64 * 1024  # multipart framing allowance
    raw = request.headers.get("content-length")
    if raw is None or not raw.isdigit():
        raise LengthRequired("Uploads must declare their size (Content-Length).")
    if int(raw) > limit:
        raise PayloadTooLarge(f"Uploads are limited to {settings.max_upload_mb} MB.")
