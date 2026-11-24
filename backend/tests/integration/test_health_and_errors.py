from fastapi import APIRouter
from fastapi.testclient import TestClient

from insightflow.api.app import create_app
from insightflow.core.errors import NotFoundError
from insightflow.core.settings import Settings


def _client(settings: Settings) -> TestClient:
    app = create_app(settings)
    router = APIRouter()

    @router.get("/boom/not-found")
    def not_found() -> None:
        raise NotFoundError("Dataset not found.")

    @router.get("/boom/crash")
    def crash() -> None:
        raise RuntimeError("secret path /etc/x")

    @router.post("/boom/mutate")
    def mutate() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def test_health_ok_with_correlation_id(settings: Settings) -> None:
    r = _client(settings).get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert r.headers["X-Correlation-ID"]


def test_incoming_correlation_id_is_echoed_if_safe(settings: Settings) -> None:
    c = _client(settings)
    assert (
        c.get("/health", headers={"X-Correlation-ID": "abc-123"}).headers["X-Correlation-ID"]
        == "abc-123"
    )
    assert (
        c.get("/health", headers={"X-Correlation-ID": "bad id\n"}).headers["X-Correlation-ID"]
        != "bad id\n"
    )


def test_app_error_is_problem_json(settings: Settings) -> None:
    r = _client(settings).get("/boom/not-found")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["type"] == "/errors/not-found"
    assert body["status"] == 404
    assert body["detail"] == "Dataset not found."
    assert body["correlation_id"] == r.headers["X-Correlation-ID"]


def test_unhandled_error_hides_internals(settings: Settings) -> None:
    r = _client(settings).get("/boom/crash")
    assert r.status_code == 500
    assert "secret" not in r.text
    assert r.json()["type"] == "/errors/internal"


def test_mutation_requires_client_header(
    settings: Settings, client_headers: dict[str, str]
) -> None:
    c = _client(settings)
    r = c.post("/boom/mutate")
    assert r.status_code == 403
    assert r.json()["type"] == "/errors/client-header-required"
    assert c.post("/boom/mutate", headers=client_headers).status_code == 200


def test_untrusted_host_rejected(settings: Settings) -> None:
    r = _client(settings).get("/health", headers={"Host": "evil.com"})
    assert r.status_code == 400
