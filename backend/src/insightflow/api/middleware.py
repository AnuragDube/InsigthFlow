"""Cross-cutting HTTP behaviour: correlation ids, client-header CSRF guard, error mapping."""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from insightflow.core.errors import AppError
from insightflow.core.logging import correlation_id

log = logging.getLogger(__name__)

CLIENT_HEADER = "X-InsightFlow-Client"
_SAFE_CID = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def problem(status: int, type_slug: str, title: str, detail: str, **extra: object) -> JSONResponse:
    body = {
        "type": f"/errors/{type_slug}",
        "title": title,
        "status": status,
        "detail": detail,
        "correlation_id": correlation_id.get(),
        **extra,
    }
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def correlation_and_client_guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get("X-Correlation-ID", "")
        cid = incoming if _SAFE_CID.match(incoming) else uuid.uuid4().hex
        token = correlation_id.set(cid)
        try:
            # A cross-site page can send a "simple" POST without a CORS preflight, but it cannot
            # add a custom header without one; strict CORS then blocks it (SECURITY.md §1a).
            if request.method in _MUTATING and request.headers.get(CLIENT_HEADER) != "web":
                response: Response = problem(
                    403,
                    "client-header-required",
                    "Forbidden",
                    f"Mutating requests must send the {CLIENT_HEADER} header.",
                )
            else:
                try:
                    response = await call_next(request)
                except Exception:  # last-resort guard: never leak internals
                    log.exception("unhandled error")
                    response = problem(500, "internal", "Internal error", "Something went wrong.")
            response.headers["X-Correlation-ID"] = cid
            return response
        finally:
            correlation_id.reset(token)

    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        return problem(exc.status, exc.type_slug, exc.title, exc.detail, **exc.extra)

    @app.exception_handler(RequestValidationError)
    async def request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        return problem(
            422, "validation-failed", "Validation failed", "Invalid request.", errors=errors
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return problem(exc.status_code, "http", "HTTP error", str(exc.detail))

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", exc_info=exc)
        return problem(500, "internal", "Internal error", "Something went wrong.")
