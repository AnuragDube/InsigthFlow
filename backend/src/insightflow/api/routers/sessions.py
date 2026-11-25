"""Browser session exchange for an explicitly configured sign-in integration."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.engine import Engine

from insightflow.api.authorization_code import LOGIN_SECONDS, STATE_COOKIE, AuthorizationCodeFlow
from insightflow.api.deps import IdentityResolver, get_engine
from insightflow.core.context import VerifiedIdentity
from insightflow.core.errors import AuthenticationRequired, NotFoundError
from insightflow.metadata.browser_sessions import (
    COOKIE_NAME,
    SESSION_SECONDS,
    issue_session,
    revoke_session,
    session_digest,
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
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    _set_session(request, engine, identity, response)
    return response


def _set_session(
    request: Request,
    engine: Engine,
    identity: VerifiedIdentity,
    response: Response,
    *,
    prior_digest: str | None = None,
) -> None:
    with session_scope(engine) as session:
        token = issue_session(
            session, identity, request.cookies.get(COOKIE_NAME), prior_digest=prior_digest
        )
    response.set_cookie(
        COOKIE_NAME, token, max_age=SESSION_SECONDS, secure=True, httponly=True, samesite="strict"
    )


def _code_flow(request: Request) -> AuthorizationCodeFlow:
    flow: AuthorizationCodeFlow | None = request.app.state.authorization_code_flow
    if flow is None:
        raise NotFoundError("Interactive sign-in is unavailable.")
    return flow


@router.get("")
def sign_in_options(request: Request) -> dict[str, bool]:
    return {"interactive": request.app.state.authorization_code_flow is not None}


@router.get("/login")
def authorization_redirect(request: Request, workspace: UUID) -> RedirectResponse:
    state, location = _code_flow(request).start(
        workspace,
        request.cookies.get(STATE_COOKIE),
        session_digest(request.cookies.get(COOKIE_NAME)),
    )
    response = RedirectResponse(location, status_code=303, headers={"Cache-Control": "no-store"})
    response.set_cookie(
        STATE_COOKIE, state, max_age=LOGIN_SECONDS, secure=True, httponly=True, samesite="lax"
    )
    return response


@router.get("/callback")
def authorization_callback(
    request: Request, engine: Eng, state: str = "", code: str = ""
) -> RedirectResponse:
    if (
        len(request.query_params.getlist("state")) != 1
        or len(request.query_params.getlist("code")) != 1
    ):
        raise AuthenticationRequired("Sign-in could not be completed. Start again.")
    identity, prior_digest = _code_flow(request).finish(
        state, request.cookies.get(STATE_COOKIE, ""), code
    )
    response = RedirectResponse("/", status_code=303, headers={"Cache-Control": "no-store"})
    _set_session(request, engine, identity, response, prior_digest=prior_digest)
    response.delete_cookie(STATE_COOKIE, secure=True, httponly=True, samesite="lax")
    return response


@router.delete("", status_code=204)
def sign_out(request: Request, engine: Eng) -> Response:
    flow: AuthorizationCodeFlow | None = request.app.state.authorization_code_flow
    if flow is None:
        _sign_in_resolver(request)
    else:
        flow.cancel(request.cookies.get(STATE_COOKIE))
    with session_scope(engine) as session:
        revoke_session(session, request.cookies.get(COOKIE_NAME))
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    response.delete_cookie(COOKIE_NAME, secure=True, httponly=True, samesite="strict")
    if flow is not None:
        response.delete_cookie(STATE_COOKIE, secure=True, httponly=True, samesite="lax")
    return response
