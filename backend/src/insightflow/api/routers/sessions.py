"""Browser session exchange for an explicitly configured sign-in integration."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.engine import Engine

from insightflow.api.deps import IdentityResolver, get_engine
from insightflow.core.errors import AuthenticationRequired, NotFoundError
from insightflow.metadata.browser_sessions import (
    COOKIE_NAME,
    SESSION_SECONDS,
    issue_session,
    revoke_session,
)
from insightflow.metadata.db import session_scope

router = APIRouter(prefix="/api/v1/session", tags=["session"])
Eng = Annotated[Engine, Depends(get_engine)]


def _sign_in_resolver(request: Request) -> IdentityResolver:
    resolver: IdentityResolver | None = request.app.state.session_login_resolver
    if resolver is None:
        raise NotFoundError("Browser sessions are unavailable.")
    return resolver


@router.post("", status_code=204)
def sign_in(request: Request, engine: Eng) -> Response:
    identity = _sign_in_resolver(request)(request)
    if identity is None:
        raise AuthenticationRequired("Sign in to access this workspace.")
    with session_scope(engine) as session:
        token = issue_session(session, identity, request.cookies.get(COOKIE_NAME))
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    response.set_cookie(
        COOKIE_NAME, token, max_age=SESSION_SECONDS, secure=True, httponly=True, samesite="strict"
    )
    return response


@router.delete("", status_code=204)
def sign_out(request: Request, engine: Eng) -> Response:
    _sign_in_resolver(request)
    with session_scope(engine) as session:
        revoke_session(session, request.cookies.get(COOKIE_NAME))
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    response.delete_cookie(COOKIE_NAME, secure=True, httponly=True, samesite="strict")
    return response
