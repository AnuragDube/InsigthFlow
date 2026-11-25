from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient

from insightflow.api.access_tokens import AccessTokenResolver
from insightflow.api.app import create_app
from insightflow.api.authorization_code import STATE_COOKIE, AuthorizationCodeFlow
from insightflow.core.context import VerifiedIdentity
from insightflow.core.settings import Settings
from insightflow.metadata.bootstrap import ensure_org
from insightflow.metadata.browser_sessions import COOKIE_NAME
from insightflow.metadata.db import session_scope
from insightflow.metadata.memberships import set_role

ISSUER = "https://issuer.example"
CLIENT = "pilot-browser"
AUDIENCE = "insightflow-api"
SESSION = "/api/v1/session"


def test_interactive_sign_in_and_logout(settings: Settings) -> None:
    key = generate_private_key(public_exponent=65537, key_size=2048)
    verifier = AccessTokenResolver(
        issuer=ISSUER,
        audience=AUDIENCE,
        client_id=CLIENT,
        public_key_pem=key.public_key().public_bytes(
            Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
        ),
    )
    calls = 0
    challenges: list[str] = []

    def exchange(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert str(request.url) == f"{ISSUER}/token"
        fields = parse_qs(request.content.decode())
        assert fields["client_id"] == [CLIENT]
        assert fields["grant_type"] == ["authorization_code"]
        assert fields["code"] == ["mock-code"]
        assert fields["redirect_uri"] == [f"https://testserver{SESSION}/callback"]
        digest = hashlib.sha256(fields["code_verifier"][0].encode("ascii")).digest()
        assert base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=") == challenges[-1]
        now = int(datetime.now(UTC).timestamp())
        token = jwt.encode(
            {
                "iss": ISSUER,
                "sub": "pilot-user",
                "aud": AUDIENCE,
                "iat": now,
                "exp": now + 600,
                "jti": "mock-token",
                "client_id": CLIENT,
            },
            key,
            algorithm="RS256",
            headers={"typ": "at+jwt"},
        )
        return httpx.Response(200, json={"access_token": token, "token_type": "Bearer"})

    with httpx.Client(transport=httpx.MockTransport(exchange)) as transport:
        flow = AuthorizationCodeFlow(
            transport,
            verifier,
            authorization_url=f"{ISSUER}/authorize",
            token_url=f"{ISSUER}/token",
            redirect_uri=f"https://testserver{SESSION}/callback",
            client_id=CLIENT,
            scope="openid profile",
        )
        app = create_app(settings, authorization_code_flow=flow)
        with TestClient(app, base_url="https://testserver") as browser:
            with session_scope(app.state.engine) as session:
                org = ensure_org(session, "pilot", "Pilot")
                other = ensure_org(session, "other", "Other")
                set_role(session, VerifiedIdentity(ISSUER, "pilot-user", org.org_id), "viewer")

            def start(workspace: str) -> str:
                response = browser.get(
                    f"{SESSION}/login", params={"workspace": workspace}, follow_redirects=False
                )
                assert response.status_code == 303
                location = urlsplit(response.headers["location"])
                assert location.hostname == "issuer.example"
                query = parse_qs(location.query)
                assert query["code_challenge_method"] == ["S256"]
                challenges.append(query["code_challenge"][0])
                state = query["state"][0]
                assert browser.cookies[STATE_COOKIE] == state
                assert "samesite=lax" in response.headers["set-cookie"].lower()
                return state

            def callback(state: str, headers: dict[str, str] | None = None) -> httpx.Response:
                return browser.get(
                    f"{SESSION}/callback",
                    params={"state": state, "code": "mock-code"},
                    headers=headers,
                    follow_redirects=False,
                )

            assert browser.get(SESSION).json() == {"interactive": True}
            assert browser.get("/api/v1/datasets").status_code == 401
            assert callback(start(str(other.org_id))).status_code == 403
            state = start(str(org.org_id))
            assert callback("different-state").status_code == 401
            assert calls == 1

            success = callback(state)
            assert success.status_code == 303
            assert success.headers["location"] == "/"
            assert COOKIE_NAME in browser.cookies
            assert STATE_COOKIE not in browser.cookies
            assert browser.get("/api/v1/datasets").status_code == 200
            assert callback(state, {"Cookie": f"{STATE_COOKIE}={state}"}).status_code == 401
            assert calls == 2

            old_token = browser.cookies[COOKIE_NAME]
            state = start(str(org.org_id))
            # The cross-site callback can omit the Strict session cookie.
            assert callback(state, {"Cookie": f"{STATE_COOKIE}={state}"}).status_code == 303
            assert (
                browser.get(
                    "/api/v1/datasets", headers={"Cookie": f"{COOKIE_NAME}={old_token}"}
                ).status_code
                == 401
            )
            state = start(str(org.org_id))
            assert (
                browser.delete(SESSION, headers={"X-InsightFlow-Client": "web"}).status_code == 204
            )
            assert callback(state, {"Cookie": f"{STATE_COOKIE}={state}"}).status_code == 401
            assert browser.get("/api/v1/datasets").status_code == 401
