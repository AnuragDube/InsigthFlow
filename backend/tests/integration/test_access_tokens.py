from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, generate_private_key
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient

from insightflow.api.access_tokens import AccessTokenResolver
from insightflow.api.app import create_app
from insightflow.core.context import VerifiedIdentity
from insightflow.core.settings import Settings
from insightflow.metadata.bootstrap import ensure_org
from insightflow.metadata.db import session_scope
from insightflow.metadata.memberships import set_role

ISSUER = "https://issuer.example"
CLIENT = "pilot-browser"
AUDIENCE = "insightflow-api"
SESSION = "/api/v1/session"
DATASETS = "/api/v1/datasets"


@pytest.fixture(scope="module")
def signing_keys() -> tuple[RSAPrivateKey, RSAPrivateKey]:
    return (
        generate_private_key(public_exponent=65537, key_size=2048),
        generate_private_key(public_exponent=65537, key_size=2048),
    )


def test_signed_access_token_exchange_and_workspace_membership(
    settings: Settings, signing_keys: tuple[RSAPrivateKey, RSAPrivateKey]
) -> None:
    signing_key, other_key = signing_keys
    resolver = AccessTokenResolver(
        issuer=ISSUER,
        audience=AUDIENCE,
        client_id=CLIENT,
        public_key_pem=signing_key.public_key().public_bytes(
            Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
        ),
    )
    app = create_app(settings, session_login_resolver=resolver)
    with TestClient(app, base_url="https://testserver") as client:
        with session_scope(app.state.engine) as session:
            workspace = ensure_org(session, "pilot", "Pilot")
            other = ensure_org(session, "other", "Other")
            set_role(session, VerifiedIdentity(ISSUER, "pilot-user", workspace.org_id), "viewer")

        now = int(datetime.now(UTC).timestamp())
        claims = {
            "iss": ISSUER,
            "sub": "pilot-user",
            "aud": AUDIENCE,
            "iat": now,
            "exp": now + 1800,
            "jti": str(uuid4()),
            "client_id": CLIENT,
            "role": "owner",
        }

        def login(token: str, org: str = str(workspace.org_id)) -> int:
            return client.post(
                SESSION,
                headers={
                    "authorization": f"Bearer {token}",
                    "x-insightflow-workspace": org,
                    "x-insightflow-client": "web",
                },
            ).status_code

        cases = (
            (claims, other_key, "at+jwt"),
            (claims, signing_key, "JWT"),
            (claims | {"aud": "another-api"}, signing_key, "at+jwt"),
            (claims | {"iss": "https://other.example"}, signing_key, "at+jwt"),
            (claims | {"client_id": "different-client"}, signing_key, "at+jwt"),
            (claims | {"iat": now - 100, "exp": now - 1}, signing_key, "at+jwt"),
            (claims | {"iat": now + 30}, signing_key, "at+jwt"),
            (claims | {"exp": now + 3601}, signing_key, "at+jwt"),
            ({key: value for key, value in claims.items() if key != "sub"}, signing_key, "at+jwt"),
        )
        for payload, key, token_type in cases:
            token = jwt.encode(payload, key, algorithm="RS256", headers={"typ": token_type})
            assert login(token) == 401
        token = jwt.encode(claims, signing_key, algorithm="RS256", headers={"typ": "at+jwt"})
        assert login(token, "invalid workspace") == 401
        assert login(token, str(other.org_id)) == 403
        assert login(token) == 204
        assert client.get(DATASETS).status_code == 200
        assert (
            client.post(
                DATASETS, json={"name": "Denied"}, headers={"x-insightflow-client": "web"}
            ).status_code
            == 403
        )
