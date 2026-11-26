from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class OrgContext:
    """The organization a request acts for. Every repository call requires one.

    It is derived from the authenticated principal (P1) or the configured demo org (P0) —
    never from client-supplied input.
    """

    org_id: uuid.UUID
    audit_actor_ref: str | None = None


Role = Literal["owner", "editor", "viewer"]


@dataclass(frozen=True)
class VerifiedIdentity:
    """Identity established by the server's sign-in integration."""

    issuer: str
    subject: str
    org_id: uuid.UUID

    def audit_ref(self) -> str:
        """Pseudonymous reference shared by request and membership audit events."""
        actor = json.dumps([str(self.org_id), self.issuer, self.subject])
        return hashlib.sha256(actor.encode("utf-8")).hexdigest()
