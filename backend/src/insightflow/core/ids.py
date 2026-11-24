from __future__ import annotations

import uuid


def new_id() -> uuid.UUID:
    """Time-ordered UUIDv7 when available (better index locality), else random UUIDv4."""
    uuid7 = getattr(uuid, "uuid7", None)
    return uuid7() if uuid7 is not None else uuid.uuid4()
