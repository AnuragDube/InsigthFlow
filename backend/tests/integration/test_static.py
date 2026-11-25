from __future__ import annotations

from mimetypes import guess_type
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from insightflow.api.app import create_app
from insightflow.core.settings import Settings


def _dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>InsightFlow</title>", "utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", "utf-8")
    return dist


def test_serves_spa_and_assets(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def windows_mime(path: str | Path) -> tuple[str | None, str | None]:
        if Path(path).suffix == ".js":
            return "application/javascript", None
        return guess_type(path)

    monkeypatch.setattr("starlette.responses.guess_type", windows_mime)
    s = settings.model_copy(update={"frontend_dist": _dist(tmp_path)})
    with TestClient(create_app(s)) as c:
        assert "InsightFlow" in c.get("/").text
        assert "InsightFlow" in c.get("/data").text  # client-side route falls back to the SPA
        assert c.get("/assets/app.js").headers["content-type"].startswith("text/javascript")
        api_404 = c.get("/api/v1/does-not-exist")
        assert api_404.status_code == 404 and api_404.json()["type"]  # API stays JSON, not the SPA


def test_security_headers_on_pages_and_api(settings: Settings, tmp_path: Path) -> None:
    s = settings.model_copy(update={"frontend_dist": _dist(tmp_path)})
    with TestClient(create_app(s)) as c:
        for path in ("/", "/api/v1/metrics"):
            h = c.get(path).headers
            assert "default-src 'self'" in h["content-security-policy"]
            assert "frame-ancestors 'none'" in h["content-security-policy"]
            assert h["x-content-type-options"] == "nosniff"
            assert h["referrer-policy"] == "no-referrer"


def test_no_frontend_configured_means_no_spa(settings: Settings) -> None:
    with TestClient(create_app(settings)) as c:
        assert c.get("/").status_code == 404


def test_path_traversal_outside_dist_is_not_served(settings: Settings, tmp_path: Path) -> None:
    (tmp_path / "secret.txt").write_text("top secret", "utf-8")
    s = settings.model_copy(update={"frontend_dist": _dist(tmp_path)})
    with TestClient(create_app(s)) as c:
        for path in ("/../secret.txt", "/assets/../../secret.txt", "/%2e%2e/secret.txt"):
            assert "top secret" not in c.get(path).text
