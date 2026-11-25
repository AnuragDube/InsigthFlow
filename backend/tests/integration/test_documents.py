from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from insightflow.api.app import create_app
from insightflow.api.deps import get_org_context
from insightflow.core.settings import Settings
from insightflow.metadata.bootstrap import ensure_org
from insightflow.metadata.db import session_scope

H = {"X-InsightFlow-Client": "web"}
DOCS = "/api/v1/documents"


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings), raise_server_exceptions=False) as test_client:
        yield test_client


def test_document_search_cites_source_and_respects_delete(client: TestClient) -> None:
    upload = client.post(
        DOCS,
        files={"file": ("refunds.md", b"# Returns\r\nRefunds take seven business days.\r\n")},
        headers=H,
    )
    assert upload.status_code == 201
    document = upload.json()
    assert client.get(DOCS).json() == [document]

    response = client.post(
        f"{DOCS}/search", json={"question": "How many business days for refunds?"}, headers=H
    )
    assert response.status_code == 200
    assert response.json() == [
        {
            "document_id": document["id"],
            "title": "refunds.md",
            "start_line": 1,
            "end_line": 2,
            "excerpt": "# Returns\nRefunds take seven business days.",
        }
    ]
    unrelated = client.post(
        f"{DOCS}/search", json={"question": "What is the warranty period?"}, headers=H
    )
    assert unrelated.json() == []
    assert client.delete(f"{DOCS}/{document['id']}", headers=H).status_code == 204
    assert client.get(DOCS).json() == []
    assert client.post(f"{DOCS}/search", json={"question": "refunds"}, headers=H).json() == []


@pytest.mark.parametrize(
    ("name", "data", "status"),
    [
        ("notes.pdf", b"not a supported document", 422),
        ("notes.md", b"invalid \xff", 422),
        ("notes.txt", b"\x00", 422),
        ("notes.txt", b" ", 422),
        ("notes.txt", b"x" * 65_537, 413),
        ("large.txt", b"x" * 80_000, 413),
    ],
)
def test_document_upload_limits(client: TestClient, name: str, data: bytes, status: int) -> None:
    result = client.post(DOCS, files={"file": (name, data)}, headers=H)
    assert result.status_code == status
    assert result.headers["content-type"].startswith("application/problem+json")
    assert client.get(DOCS).json() == []


def test_corpus_is_scoped_before_search_and_delete(settings: Settings) -> None:
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        with session_scope(app.state.engine) as session:
            other_org = ensure_org(session, "other", "Other organization")
        result = client.post(
            DOCS, files={"file": ("private.txt", b"Refunds take seven days.")}, headers=H
        )
        doc = result.json()
        app.dependency_overrides[get_org_context] = lambda: other_org
        assert client.get(DOCS).json() == []
        assert client.post(f"{DOCS}/search", json={"question": "refunds"}, headers=H).json() == []
        assert client.delete(f"{DOCS}/{doc['id']}", headers=H).status_code == 404
        app.dependency_overrides.clear()
        assert client.get(DOCS).json() == [doc]
