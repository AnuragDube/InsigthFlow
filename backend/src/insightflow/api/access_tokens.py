"""Verify access tokens intended for the InsightFlow API."""

from __future__ import annotations

from urllib.parse import urlsplit
from uuid import UUID

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from fastapi import Request

from insightflow.core.context import VerifiedIdentity

_MAX_TOKEN_LENGTH = 8192
_MAX_TOKEN_LIFETIME = 60 * 60
_REQUIRED_CLAIMS = ("iss", "sub", "aud", "exp", "iat", "jti", "client_id")


class AccessTokenResolver:
    """Accept RFC 9068 RS256 access tokens signed by one configured issuer key."""

    def __init__(
        self, *, issuer: str, audience: str, client_id: str, public_key_pem: bytes
    ) -> None:
        url = urlsplit(issuer)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username is not None
            or url.query
            or url.fragment
        ):
            raise ValueError("Configure an HTTPS token issuer URL.")
        if not audience.strip() or not client_id.strip():
            raise ValueError("Configure the expected API audience and OAuth client ID.")
        key = load_pem_public_key(public_key_pem)
        if not isinstance(key, RSAPublicKey) or key.key_size < 2048:
            raise ValueError("Configure an RSA verification key of at least 2048 bits.")
        self._issuer = issuer
        self._audience = audience
        self._client_id = client_id
        self._key = key

    def __call__(self, request: Request) -> VerifiedIdentity | None:
        authorization = request.headers.getlist("authorization")
        workspace = request.headers.getlist("x-insightflow-workspace")
        if len(authorization) != 1 or len(workspace) != 1:
            return None
        scheme, _, token = authorization[0].partition(" ")
        if scheme.casefold() != "bearer":
            return None
        try:
            org_id = UUID(workspace[0])
        except ValueError:
            return None
        return self.verify(token, org_id)

    def verify(self, token: str, org_id: UUID) -> VerifiedIdentity | None:
        if not 1 <= len(token) <= _MAX_TOKEN_LENGTH:
            return None
        try:
            verified = jwt.decode_complete(
                token,
                key=self._key,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience,
                options={"require": list(_REQUIRED_CLAIMS)},
            )
            header, claims = verified["header"], verified["payload"]
            token_type = header.get("typ")
            if (
                not isinstance(token_type, str)
                or token_type.casefold() not in {"at+jwt", "application/at+jwt"}
                or "crit" in header
                or claims["client_id"] != self._client_id
            ):
                return None
            subject, token_id = claims["sub"], claims["jti"]
            issued, expires = claims["iat"], claims["exp"]
            if (
                not isinstance(subject, str)
                or not subject.strip()
                or len(subject) > 255
                or not subject.isprintable()
                or not isinstance(token_id, str)
                or not token_id.strip()
                or type(issued) is not int
                or type(expires) is not int
                or not 0 < expires - issued <= _MAX_TOKEN_LIFETIME
            ):
                return None
        except (jwt.InvalidTokenError, TypeError, ValueError, OverflowError):
            return None
        return VerifiedIdentity(self._issuer, subject, org_id)
