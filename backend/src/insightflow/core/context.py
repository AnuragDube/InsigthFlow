from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class OrgContext:
    """The organization a request acts for. Every repository call requires one.

    It is derived from the authenticated principal (P1) or the configured demo org (P0) —
    never from client-supplied input.
    """

    org_id: uuid.UUID
