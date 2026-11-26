"""FastAPI dependencies: settings, engine, org context, request-size guard."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.engine import Engine

from insightflow.analytics.question_provider import QuestionProvider
from insightflow.core.context import OrgContext, Role, VerifiedIdentity
from insightflow.core.errors import AuthenticationRequired, ForbiddenError
from insightflow.core.settings import Settings
from insightflow.metadata.browser_sessions import COOKIE_NAME, resolve_session
from insightflow.metadata.db import session_scope
from insightflow.metadata.memberships import role_for


@dataclass(frozen=True)
class Principal:
    org_id: UUID
    role: Role
    identity: VerifiedIdentity | None = None


IdentityResolver = Callable[[Request], VerifiedIdentity | None]


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_engine(request: Request) -> Engine:
    engine: Engine = request.app.state.engine
    return engine


def get_question_provider(request: Request) -> QuestionProvider | None:
    provider: QuestionProvider | None = request.app.state.question_provider
    return provider


def get_principal(request: Request, engine: Annotated[Engine, Depends(get_engine)]) -> Principal:
    resolver: IdentityResolver | None = request.app.state.identity_resolver
    cookie_mode = (
        request.app.state.session_login_resolver is not None
        or request.app.state.authorization_code_flow is not None
    )
    if resolver is None and not cookie_mode:
        ctx: OrgContext = request.app.state.demo_ctx
        return Principal(ctx.org_id, "owner")
    identity = resolver(request) if resolver is not None else None
    with session_scope(engine) as session:
        if cookie_mode:
            identity = resolve_session(session, request.cookies.get(COOKIE_NAME, ""))
        if identity is None:
            raise AuthenticationRequired("Sign in to access this workspace.")
        role = role_for(session, identity)
    if role is None:
        raise ForbiddenError("You do not have access to this workspace.")
    return Principal(identity.org_id, role, identity)


Authenticated = Annotated[Principal, Depends(get_principal)]


def get_org_context(principal: Authenticated) -> OrgContext:
    return OrgContext(principal.org_id)


def get_editor_context(principal: Authenticated) -> OrgContext:
    if principal.role not in {"owner", "editor"}:
        raise ForbiddenError("This action requires an editor or owner role.")
    if principal.identity is None:
        return OrgContext(principal.org_id)
    identity = principal.identity
    # The workspace and issuer namespace the subject. Store no raw provider identifiers.
    actor = json.dumps([str(principal.org_id), identity.issuer, identity.subject])
    return OrgContext(principal.org_id, hashlib.sha256(actor.encode("utf-8")).hexdigest())
