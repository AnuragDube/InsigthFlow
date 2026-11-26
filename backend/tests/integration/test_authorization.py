from __future__ import annotations

import uuid

from fastapi import Request
from fastapi.testclient import TestClient

from insightflow.api.app import create_app
from insightflow.core.context import VerifiedIdentity
from insightflow.core.settings import Settings
from insightflow.metadata.bootstrap import ensure_org
from insightflow.metadata.db import session_scope
from insightflow.metadata.memberships import set_role
from insightflow.metadata.models import Organization
from pipeline_helpers import FIX

H = {"X-InsightFlow-Client": "web"}
DATASETS = "/api/v1/datasets"
DOCUMENTS = "/api/v1/documents"


def test_principal_scopes_reads_and_requires_editor_for_writes(settings: Settings) -> None:
    identities: dict[str, VerifiedIdentity] = {}

    def resolve(request: Request) -> VerifiedIdentity | None:
        return identities.get(request.headers.get("authorization", ""))

    app = create_app(settings, identity_resolver=resolve)
    with TestClient(app, raise_server_exceptions=False) as client:
        with session_scope(app.state.engine) as session:
            first = ensure_org(session, "first", "First organization").org_id
            second = ensure_org(session, "second", "Second organization").org_id
            suspended = ensure_org(session, "suspended", "Suspended organization").org_id
            org = session.get(Organization, suspended)
            assert org is not None
            org.status = "suspended"
        identities.update(
            {
                "editor": VerifiedIdentity("test-issuer", "editor", first),
                "viewer": VerifiedIdentity("test-issuer", "viewer", first),
                "other": VerifiedIdentity("test-issuer", "editor", second),
                "suspended": VerifiedIdentity("test-issuer", "viewer", suspended),
                "unknown": VerifiedIdentity("test-issuer", "editor", uuid.uuid4()),
                "unassigned": VerifiedIdentity("test-issuer", "unassigned", first),
                "different-issuer": VerifiedIdentity("different-issuer", "editor", first),
            }
        )
        with session_scope(app.state.engine) as session:
            set_role(session, identities["editor"], "editor")
            set_role(session, identities["viewer"], "viewer")
            set_role(session, identities["other"], "editor")
            set_role(session, identities["suspended"], "owner")
        unauthenticated = client.get(DATASETS, headers={"X-Organization": str(first)})
        assert unauthenticated.status_code == 401
        assert unauthenticated.json()["type"] == "/errors/authentication-required"
        for identity in ("unknown", "suspended", "unassigned", "different-issuer"):
            assert client.get(DATASETS, headers={"Authorization": identity}).status_code == 403

        editor = {**H, "Authorization": "editor"}
        viewer = {**H, "Authorization": "viewer"}
        other = {**H, "Authorization": "other", "X-Organization": str(first)}
        created = client.post(DATASETS, json={"name": "Only first"}, headers=editor)
        assert created.status_code == 201
        ds = f"{DATASETS}/{created.json()['id']}"
        uploaded = client.post(
            f"{ds}/uploads",
            files={"file": ("batch.csv", (FIX / "batch_b.csv").read_bytes())},
            headers=editor,
        )
        assert uploaded.status_code == 201
        usage = "/api/v1/workspace/storage"
        assert client.get(usage).status_code == 401
        assert client.get(usage, headers=viewer).json()["retained_csv_bytes"] > 0
        assert client.get(usage, headers=other).json()["retained_csv_bytes"] == 0
        batch = f"{ds}/ingestions/{uploaded.json()['ingestion']['id']}"
        run = f"/api/v1/pipeline-runs/{uploaded.json()['run_id']}"
        doc = client.post(
            DOCUMENTS, files={"file": ("private.txt", b"Refunds take seven days.")}, headers=editor
        )
        assert doc.status_code == 201
        doc_path = f"{DOCUMENTS}/{doc.json()['id']}"

        listed = client.get(DATASETS, headers=viewer).json()["items"]
        assert [(item["id"], item["published_run_id"]) for item in listed] == [
            (created.json()["id"], uploaded.json()["run_id"])
        ]
        assert client.get(DOCUMENTS, headers=viewer).json() == [doc.json()]
        assert (
            client.post(f"{ds}/questions", json={"question": "Orders"}, headers=viewer).json()[
                "value"
            ]
            == 4
        )
        search = {"question": "refunds"}
        assert len(client.post(f"{DOCUMENTS}/search", json=search, headers=viewer).json()) == 1

        mutations = (
            ("POST", DATASETS, {"json": {"name": "Viewer cannot create"}}),
            ("POST", f"{ds}/uploads", {"files": {"file": ("a.csv", b"x")}}),
            ("POST", f"{ds}/load-sample", {}),
            ("PATCH", batch, {"json": {"is_active": False}}),
            ("POST", f"{ds}/pipeline-runs", {}),
            ("POST", DOCUMENTS, {"files": {"file": ("a.txt", b"x")}}),
            ("DELETE", doc_path, {}),
        )
        for method, path, payload in mutations:
            response = client.request(method, path, headers=viewer, **payload)
            assert response.status_code == 403, (path, response.text)

        for path in (f"{ds}/dashboard", f"{ds}/ingestions", run, f"{run}/quality"):
            assert client.get(path, headers=other).status_code == 404
        assert client.get(DATASETS, headers=other).json()["items"] == []
        assert client.get(DOCUMENTS, headers=other).json() == []
        assert client.post(f"{DOCUMENTS}/search", json=search, headers=other).json() == []
        assert (
            client.post(f"{ds}/questions", json={"question": "Orders"}, headers=other).status_code
            == 404
        )
        assert client.post(f"{ds}/load-sample", headers=other).status_code == 404
        assert client.delete(doc_path, headers=other).status_code == 404
        assert client.delete(doc_path, headers=editor).status_code == 204

        with session_scope(app.state.engine) as session:
            set_role(session, identities["editor"], "viewer")
        assert client.post(DATASETS, headers=editor, json={"name": "Denied"}).status_code == 403
        assert client.get(DATASETS, headers=editor).status_code == 200
        with session_scope(app.state.engine) as session:
            set_role(session, identities["editor"], None)
        assert client.get(DATASETS, headers=editor).status_code == 403
        assert client.get(DATASETS, headers=other).status_code == 200
