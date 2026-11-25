"""Opaque browser sessions. Only token digests are persisted."""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from insightflow.core.context import VerifiedIdentity
from insightflow.core.errors import ForbiddenError
from insightflow.metadata.memberships import role_for
from insightflow.metadata.models import BrowserSession

COOKIE_NAME = "__Host-insightflow_session"
SESSION_SECONDS = 8 * 60 * 60
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def resolve_session(session: Session, token: str) -> VerifiedIdentity | None:
    if not _TOKEN_PATTERN.fullmatch(token):
        return None
    record = session.scalar(
        select(BrowserSession).where(
            BrowserSession.token_hash == _digest(token),
            BrowserSession.expires_at > datetime.now(UTC),
        )
    )
    if record is None:
        return None
    return VerifiedIdentity(record.issuer, record.subject, record.org_id)


def revoke_session(session: Session, token: str | None) -> None:
    if token is not None and _TOKEN_PATTERN.fullmatch(token):
        session.execute(delete(BrowserSession).where(BrowserSession.token_hash == _digest(token)))


def issue_session(session: Session, identity: VerifiedIdentity, previous: str | None) -> str:
    if role_for(session, identity) is None:
        raise ForbiddenError("You do not have access to this workspace.")
    now = datetime.now(UTC)
    session.execute(delete(BrowserSession).where(BrowserSession.expires_at <= now))
    revoke_session(session, previous)
    token = secrets.token_urlsafe(32)
    session.add(
        BrowserSession(
            token_hash=_digest(token),
            org_id=identity.org_id,
            issuer=identity.issuer,
            subject=identity.subject,
            expires_at=now + timedelta(seconds=SESSION_SECONDS),
        )
    )
    return token
