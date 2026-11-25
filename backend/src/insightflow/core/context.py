from __future__ import annotations

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


Role = Literal["owner", "editor", "viewer"]


@dataclass(frozen=True)
class VerifiedIdentity:
    """Identity established by the server's sign-in integration."""

    issuer: str
    subject: str
    org_id: uuid.UUID
