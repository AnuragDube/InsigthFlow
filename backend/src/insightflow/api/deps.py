"""FastAPI dependencies: settings, engine, org context, request-size guard."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends, Request
from sqlalchemy.engine import Engine

from insightflow.analytics.question_provider import QuestionProvider
from insightflow.core.context import OrgContext
from insightflow.core.errors import AuthenticationRequired, ForbiddenError
from insightflow.core.settings import Settings
from insightflow.metadata.db import session_scope
from insightflow.metadata.models import Organization


@dataclass(frozen=True)
class Principal:
    org_id: uuid.UUID
    role: Literal["owner", "editor", "viewer"]


PrincipalResolver = Callable[[Request], Principal | None]


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
    resolver: PrincipalResolver | None = request.app.state.principal_resolver
    if resolver is None:
        ctx: OrgContext = request.app.state.demo_ctx
        return Principal(ctx.org_id, "owner")
    principal = resolver(request)
    if principal is None:
        raise AuthenticationRequired("Sign in to access this workspace.")
    with session_scope(engine) as session:
        organization = session.get(Organization, principal.org_id)
        if organization is None or organization.status != "active":
            raise ForbiddenError("This workspace is unavailable.")
    if principal.role not in {"owner", "editor", "viewer"}:
        raise ForbiddenError("You do not have access to this workspace.")
    return principal


Authenticated = Annotated[Principal, Depends(get_principal)]


def get_org_context(principal: Authenticated) -> OrgContext:
    return OrgContext(principal.org_id)


def get_editor_context(principal: Authenticated) -> OrgContext:
    if principal.role not in {"owner", "editor"}:
        raise ForbiddenError("This action requires an editor or owner role.")
    return OrgContext(principal.org_id)
