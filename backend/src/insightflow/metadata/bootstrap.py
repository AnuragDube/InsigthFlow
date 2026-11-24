from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from insightflow.core.context import OrgContext
from insightflow.core.ids import new_id
from insightflow.metadata.models import Organization


def ensure_org(session: Session, slug: str, name: str) -> OrgContext:
    org = session.scalars(select(Organization).where(Organization.slug == slug)).first()
    if org is None:
        org = Organization(id=new_id(), slug=slug, name=name)
        session.add(org)
        session.flush()
    return OrgContext(org.id)


def ensure_demo_org(session: Session, slug: str) -> OrgContext:
    """P0 has no authentication: all requests act for this single local demo org."""
    return ensure_org(session, slug, "Demo organization")
