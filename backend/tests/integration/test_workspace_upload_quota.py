from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from insightflow.api.app import create_app
from insightflow.core.errors import WorkspaceUploadQuotaExceeded
from insightflow.core.settings import Settings
from insightflow.ingestion import service
from insightflow.metadata.db import session_scope
from insightflow.metadata.repositories import IngestionRepo
from insightflow.warehouse.paths import OrgPaths

H = {"X-InsightFlow-Client": "web"}


def _csv() -> bytes:
    header = "Invoice,StockCode,Description,Quantity,InvoiceDate,Price,Customer ID,Country\n"
    description = "x" * 900
    return (
        header
        + "".join(
            f"{1000 + i},85123A,{description},1,2010-12-01 08:00:00,2.00,17850,United Kingdom\n"
            for i in range(700)
        )
    ).encode()


def test_workspace_quota_preserves_publication_and_allows_duplicate(settings: Settings) -> None:
    settings = settings.model_copy(update={"max_workspace_upload_mb": 1})
    payload = _csv()
    with TestClient(create_app(settings)) as client:
        usage = "/api/v1/workspace/storage"
        assert client.get(usage).json() == {"retained_csv_bytes": 0, "limit_bytes": 1048576}
        first_id, second_id = [
            client.post("/api/v1/datasets", headers=H, json={"name": name}).json()["id"]
            for name in ("First", "Second")
        ]
        files = {"file": ("batch.csv", payload)}
        first = client.post(f"/api/v1/datasets/{first_id}/uploads", headers=H, files=files)
        assert first.status_code == 201
        assert first.json()["run_id"]
        duplicate = client.post(f"/api/v1/datasets/{first_id}/uploads", headers=H, files=files)
        assert duplicate.status_code == 200
        denied = client.post(f"/api/v1/datasets/{second_id}/uploads", headers=H, files=files)
        assert denied.status_code == 409
        assert denied.json()["type"] == "/errors/workspace-upload-quota"
        dashboard = client.get(f"/api/v1/datasets/{first_id}/dashboard").raise_for_status().json()
        assert dashboard["freshness"]["run_id"] == first.json()["run_id"]
        assert client.get(f"/api/v1/datasets/{second_id}/ingestions").json()["items"] == []
        assert client.get(usage).json() == {
            "retained_csv_bytes": len(payload),
            "limit_bytes": 1048576,
        }


def test_concurrent_datasets_cannot_exceed_workspace_quota(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = settings.model_copy(update={"max_workspace_upload_mb": 1})
    ready = Barrier(2)
    original = service._write_bronze

    def concurrent_write(path: Path, out_dir: Path, ingestion_id: UUID) -> int:
        ready.wait(timeout=10)
        return original(path, out_dir, ingestion_id)

    monkeypatch.setattr(service, "_write_bronze", concurrent_write)
    with TestClient(create_app(settings)) as client:
        app = client.app
        ctx, engine = app.state.demo_ctx, app.state.engine
        payload = _csv()
        dataset_ids = [
            UUID(client.post("/api/v1/datasets", headers=H, json={"name": name}).json()["id"])
            for name in ("One", "Two")
        ]

        def upload(dataset: UUID) -> bool:
            try:
                return service.ingest_file(
                    ctx, engine, settings, dataset, io.BytesIO(payload), "batch.csv"
                ).created
            except WorkspaceUploadQuotaExceeded:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(upload, dataset_ids)) == [False, True]
        with session_scope(engine) as session:
            assert IngestionRepo(session).stored_bytes(ctx) == len(payload)
        bronze = OrgPaths(settings.data_dir, ctx.org_id).root / "bronze"
        assert len(list(bronze.rglob("raw.csv"))) == 1
