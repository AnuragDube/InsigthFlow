from __future__ import annotations

import logging
import tempfile

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

router = APIRouter(tags=["health"])
log = logging.getLogger(__name__)


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness: the process is up. Does not touch dependencies."""
    return {"status": "ok"}


@router.get("/ready")
def ready(request: Request) -> JSONResponse:
    """Readiness: the metadata DB answers and the data directory is writable."""
    checks: dict[str, str] = {}
    try:
        with request.app.state.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        log.exception("readiness: database check failed")
        checks["database"] = "error"
    try:
        data_dir = request.app.state.settings.data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=data_dir):
            pass
        checks["data_dir"] = "ok"
    except OSError:
        log.exception("readiness: data dir check failed")
        checks["data_dir"] = "error"
    ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        {"status": "ready" if ok else "not_ready", "checks": checks}, status_code=200 if ok else 503
    )
