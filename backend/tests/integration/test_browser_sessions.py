from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from insightflow.api.app import create_app
from insightflow.core.context import VerifiedIdentity
from insightflow.core.settings import Settings
from insightflow.metadata.bootstrap import ensure_org
from insightflow.metadata.browser_sessions import COOKIE_NAME, SESSION_SECONDS
from insightflow.metadata.db import session_scope
from insightflow.metadata.memberships import set_role
from insightflow.metadata.models import BrowserSession

H = {"X-InsightFlow-Client": "web"}
SESSION = "/api/v1/session"
DATASETS = "/api/v1/datasets"


def test_browser_session_exchange_lifecycle(settings: Settings) -> None:
    identity: VerifiedIdentity | None = None

    def sign_in(request: Request) -> VerifiedIdentity | None:
        return identity if request.headers.get("authorization") == "verified-by-test" else None

    app = create_app(settings, session_login_resolver=sign_in)
    auth = {**H, "Authorization": "verified-by-test"}
    with TestClient(app, base_url="https://testserver") as client:
        with session_scope(app.state.engine) as session:
            org = ensure_org(session, "pilot", "Pilot")
            identity = VerifiedIdentity("test-issuer", "pilot-user", org.org_id)
        assert client.get(DATASETS, headers=auth).status_code == 401
        assert client.post(SESSION, headers=H).status_code == 401
        assert client.post(SESSION, headers=auth).status_code == 403
        with session_scope(app.state.engine) as session:
            set_role(session, identity, "editor")

        login = client.post(SESSION, headers=auth)
        assert login.status_code == 204
        assert login.headers["cache-control"] == "no-store"
        cookie = login.headers["set-cookie"].lower()
        for attribute in (
            "secure",
            "httponly",
            "samesite=strict",
            "path=/",
            f"max-age={SESSION_SECONDS}",
        ):
            assert attribute in cookie
        assert "domain=" not in cookie
        first_token = client.cookies[COOKIE_NAME]
        with session_scope(app.state.engine) as session:
            assert (
                session.scalar(select(BrowserSession.token_hash))
                == hashlib.sha256(first_token.encode("ascii")).hexdigest()
            )
        assert client.post(DATASETS, headers=H, json={"name": "Pilot dataset"}).status_code == 201

        assert client.post(SESSION, headers=auth).status_code == 204
        second_token = client.cookies[COOKIE_NAME]
        assert second_token != first_token
        stale_cookie = {"Cookie": f"{COOKIE_NAME}={first_token}"}
        assert client.get(DATASETS, headers=stale_cookie).status_code == 401
        assert client.get(DATASETS).status_code == 200

        with session_scope(app.state.engine) as session:
            set_role(session, identity, "viewer")
        assert client.post(DATASETS, headers=H, json={"name": "Denied"}).status_code == 403
        assert client.get(DATASETS).status_code == 200
        assert client.delete(SESSION).status_code == 403
        logout = client.delete(SESSION, headers=H)
        assert logout.status_code == 204
        assert "max-age=0" in logout.headers["set-cookie"].lower()
        latest_cookie = {"Cookie": f"{COOKIE_NAME}={second_token}"}
        assert client.get(DATASETS, headers=latest_cookie).status_code == 401

        assert client.post(SESSION, headers=auth).status_code == 204
        with session_scope(app.state.engine) as session:
            session.execute(
                update(BrowserSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
        assert client.get(DATASETS).status_code == 401
        assert client.post(SESSION, headers=auth).status_code == 204

        with session_scope(app.state.engine) as session:
            set_role(session, identity, None)
        with session_scope(app.state.engine) as session:
            set_role(session, identity, "editor")
        assert client.get(DATASETS).status_code == 401


def test_browser_sessions_are_opt_in(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        assert client.post(SESSION, headers=H).status_code == 404
        assert client.delete(SESSION, headers=H).status_code == 404
        assert client.get(DATASETS).status_code == 200

    def absent_identity(_request: Request) -> None:
        return None

    with pytest.raises(ValueError, match="either direct identity resolution or browser sessions"):
        create_app(
            settings, identity_resolver=absent_identity, session_login_resolver=absent_identity
        )
