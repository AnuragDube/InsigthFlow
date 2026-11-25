"""Persist and resolve workspace roles for verified identities."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from insightflow.core.context import Role, VerifiedIdentity
from insightflow.core.errors import NotFoundError, ValidationFailed
from insightflow.metadata.models import Organization, WorkspaceMembership


def role_for(session: Session, identity: VerifiedIdentity) -> Role | None:
    return session.scalar(
        select(WorkspaceMembership.role)
        .join(Organization, WorkspaceMembership.org_id == Organization.id)
        .where(
            Organization.status == "active",
            WorkspaceMembership.org_id == identity.org_id,
            WorkspaceMembership.issuer == identity.issuer,
            WorkspaceMembership.subject == identity.subject,
        )
    )


def set_role(session: Session, identity: VerifiedIdentity, role: Role | None) -> None:
    if not all(
        value.isprintable() and 1 <= len(value) <= 255
        for value in (identity.issuer, identity.subject)
    ):
        raise ValidationFailed("Issuer and subject must contain 1 to 255 printable characters.")
    # A no-op write serializes grants and revocations on SQLite and PostgreSQL.
    session.execute(
        update(Organization)
        .where(Organization.id == identity.org_id)
        .values(status=Organization.status)
    )
    if session.get(Organization, identity.org_id) is None:
        raise NotFoundError("Workspace not found.")
    membership = session.get(
        WorkspaceMembership, (identity.org_id, identity.issuer, identity.subject)
    )
    if role is None:
        if membership is not None:
            session.delete(membership)
    elif membership is None:
        session.add(
            WorkspaceMembership(
                org_id=identity.org_id, issuer=identity.issuer, subject=identity.subject, role=role
            )
        )
    else:
        membership.role = role
