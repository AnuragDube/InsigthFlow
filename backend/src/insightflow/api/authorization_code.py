"""Configured OAuth authorization-code exchange with PKCE for a single-process pilot."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from threading import Lock
from urllib.parse import urlencode, urlsplit
from uuid import UUID

import httpx

from insightflow.api.access_tokens import AccessTokenResolver
from insightflow.core.context import VerifiedIdentity
from insightflow.core.errors import AuthenticationRequired, ConflictError

STATE_COOKIE = "__Host-insightflow_oauth_state"
LOGIN_SECONDS = 300
_MAX_PENDING = 256
_MAX_RESPONSE_BYTES = 32_768


@dataclass(frozen=True)
class PendingLogin:
    workspace: UUID
    verifier: str
    expires: float
    prior_digest: str | None


class AuthorizationCodeFlow:
    """Exchange codes at configured HTTPS endpoints and verify the resulting access token."""

    def __init__(
        self,
        client: httpx.Client,
        verifier: AccessTokenResolver,
        *,
        authorization_url: str,
        token_url: str,
        redirect_uri: str,
        client_id: str,
        scope: str,
    ) -> None:
        for url in (authorization_url, token_url, redirect_uri):
            parsed = urlsplit(url)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("OAuth endpoints and callback must use fixed HTTPS URLs.")
        if urlsplit(redirect_uri).path != "/api/v1/session/callback":
            raise ValueError("Configure the exact /api/v1/session/callback URL.")
        self._client = client
        self._verifier = verifier
        self._authorization_url = authorization_url
        self._token_url = token_url
        self._redirect_uri = redirect_uri
        self._client_id = client_id
        self._scope = scope
        self._pending: dict[str, PendingLogin] = {}
        self._lock = Lock()

    def start(
        self, workspace: UUID, previous_state: str | None, prior_digest: str | None
    ) -> tuple[str, str]:
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(32)
        now = time.monotonic()
        with self._lock:
            self._pending = {
                key: login for key, login in self._pending.items() if login.expires > now
            }
            if previous_state is not None:
                self._pending.pop(previous_state, None)
            if len(self._pending) >= _MAX_PENDING:
                raise ConflictError("Too many sign-in attempts are waiting. Try again shortly.")
            self._pending[state] = PendingLogin(
                workspace, verifier, now + LOGIN_SECONDS, prior_digest
            )
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self._client_id,
                "redirect_uri": self._redirect_uri,
                "scope": self._scope,
                "state": state,
                "code_challenge": challenge.decode("ascii").rstrip("="),
                "code_challenge_method": "S256",
            }
        )
        return state, f"{self._authorization_url}?{query}"

    def cancel(self, browser_state: str | None) -> None:
        if browser_state is not None:
            with self._lock:
                self._pending.pop(browser_state, None)

    def finish(
        self, state: str, browser_state: str, code: str
    ) -> tuple[VerifiedIdentity, str | None]:
        generic = "Sign-in could not be completed. Start again."
        if (
            not state.isascii()
            or len(state) != 43
            or not browser_state.isascii()
            or not secrets.compare_digest(state, browser_state)
            or not 1 <= len(code) <= 2048
        ):
            raise AuthenticationRequired(generic)
        with self._lock:
            login = self._pending.pop(state, None)
        if login is None or login.expires <= time.monotonic():
            raise AuthenticationRequired(generic)
        try:
            with self._client.stream(
                "POST",
                self._token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._redirect_uri,
                    "client_id": self._client_id,
                    "code_verifier": login.verifier,
                },
                timeout=5.0,
                follow_redirects=False,
            ) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes(chunk_size=_MAX_RESPONSE_BYTES):
                    body.extend(chunk)
                    if len(body) > _MAX_RESPONSE_BYTES:
                        raise ValueError("OAuth token response too large.")
            payload = json.loads(body)
            token = payload["access_token"]
            token_type = payload["token_type"]
            if not isinstance(token, str) or not isinstance(token_type, str):
                raise ValueError("Invalid token response.")
            identity = (
                self._verifier.verify(token, login.workspace)
                if token_type.casefold() == "bearer"
                else None
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise AuthenticationRequired(generic) from None
        if identity is None:
            raise AuthenticationRequired(generic)
        return identity, login.prior_digest
