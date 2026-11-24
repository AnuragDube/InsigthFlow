"""Domain errors that map to RFC 9457 problem+json responses.

Raise these from services; the API layer turns them into safe HTTP responses.
``detail`` must be safe to show to users (no paths, SQL or secrets).
"""

from __future__ import annotations


class AppError(Exception):
    status: int = 500
    type_slug: str = "internal"
    title: str = "Internal error"

    def __init__(self, detail: str, *, extra: dict[str, object] | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.extra = extra or {}


class NotFoundError(AppError):
    status, type_slug, title = 404, "not-found", "Not found"


class ConflictError(AppError):
    status, type_slug, title = 409, "conflict", "Conflict"


class ValidationFailed(AppError):
    status, type_slug, title = 422, "validation-failed", "Validation failed"


class ForbiddenError(AppError):
    status, type_slug, title = 403, "forbidden", "Forbidden"


class NoPublishedData(ConflictError):
    type_slug, title = "no-published-data", "No published data"


class PayloadTooLarge(AppError):
    status, type_slug, title = 413, "payload-too-large", "Payload too large"
