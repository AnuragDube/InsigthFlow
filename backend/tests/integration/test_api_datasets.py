from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from insightflow.api.app import create_app
from insightflow.core.settings import Settings
from insightflow.ingestion.service import ingest_file
from pipeline_helpers import FIX

H = {"X-InsightFlow-Client": "web"}


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        yield c


def _dataset(client: TestClient, name: str = "Retail") -> str:
    r = client.post("/api/v1/datasets", json={"name": name}, headers=H)
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def _upload(client: TestClient, ds: str, fixture: str) -> Any:
    with (FIX / fixture).open("rb") as f:
        return client.post(
            f"/api/v1/datasets/{ds}/uploads", files={"file": (fixture, f, "text/csv")}, headers=H
        )


def test_create_and_list_datasets(client: TestClient) -> None:
    ds = _dataset(client)
    body = client.get("/api/v1/datasets").json()
    assert [d["id"] for d in body["items"]] == [ds]
    assert body["items"][0]["domain"] == "ecommerce"
    dup = client.post("/api/v1/datasets", json={"name": "Retail"}, headers=H)
    assert dup.status_code == 409 and dup.json()["type"] == "/errors/conflict"


def test_upload_runs_pipeline_and_publishes(client: TestClient) -> None:
    ds = _dataset(client)
    r = _upload(client, ds, "batch_b.csv")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["created"] is True and body["ingestion"]["row_count"] == 8
    run = client.get(f"/api/v1/pipeline-runs/{body['run_id']}").json()
    assert run["status"] == "succeeded"
    assert [s["stage"] for s in run["stages"]] == [
        "silver", "silver_quality", "gold", "gold_quality", "publish",
    ]  # fmt: skip
    quality = client.get(f"/api/v1/pipeline-runs/{body['run_id']}/quality").json()["items"]
    assert len(quality) == 9
    assert all(q["passed"] for q in quality if q["severity"] == "blocking")
    assert client.get("/api/v1/datasets").json()["items"][0]["published_run_id"] == run["id"]


def test_reupload_returns_existing_without_new_run(client: TestClient) -> None:
    ds = _dataset(client)
    first = _upload(client, ds, "batch_b.csv").json()
    again = _upload(client, ds, "batch_b.csv")
    assert again.status_code == 200
    assert again.json()["ingestion"]["id"] == first["ingestion"]["id"]
    assert again.json()["run_id"] is None
    runs = client.get("/api/v1/pipeline-runs", params={"dataset_id": ds}).json()["items"]
    assert len(runs) == 1
    assert runs[0]["stages"][0]["stage"] == "silver"  # the list includes stage stats


def test_bad_batch_blocks_then_deactivating_it_republishes(client: TestClient) -> None:
    ds = _dataset(client)
    good = _upload(client, ds, "batch_b.csv").json()
    bad = _upload(client, ds, "batch_a.csv").json()  # 2 of 22 rows quarantined > 1% gate
    blocked = client.get(f"/api/v1/pipeline-runs/{bad['run_id']}").json()
    assert blocked["status"] == "blocked_by_quality"
    dataset = client.get("/api/v1/datasets").json()["items"][0]
    assert dataset["published_run_id"] == good["run_id"]  # previous publication untouched

    r = client.patch(
        f"/api/v1/datasets/{ds}/ingestions/{bad['ingestion']['id']}",
        json={"is_active": False},
        headers=H,
    )
    assert r.status_code == 200 and r.json()["ingestion"]["is_active"] is False
    rerun = client.get(f"/api/v1/pipeline-runs/{r.json()['run_id']}").json()
    assert rerun["status"] == "succeeded"
    ingestions = client.get(f"/api/v1/datasets/{ds}/ingestions").json()["items"]
    assert [i["is_active"] for i in ingestions] == [True, False]


def test_wrong_headers_rejected(client: TestClient) -> None:
    ds = _dataset(client)
    r = _upload(client, ds, "bad_headers.csv")
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")
    assert "Country" in r.json()["detail"]


def test_unknown_dataset_is_404_problem(client: TestClient) -> None:
    r = client.get(
        "/api/v1/pipeline-runs", params={"dataset_id": "00000000-0000-0000-0000-000000000000"}
    )
    assert r.status_code == 404 and r.json()["type"] == "/errors/not-found"


def test_upload_without_client_header_forbidden(client: TestClient) -> None:
    ds = _dataset(client)
    with (FIX / "batch_b.csv").open("rb") as f:
        r = client.post(f"/api/v1/datasets/{ds}/uploads", files={"file": ("b.csv", f)})
    assert r.status_code == 403


def test_oversized_request_rejected_before_parsing(settings: Settings, tmp_path: Path) -> None:
    small = settings.model_copy(update={"max_upload_mb": 0})
    big = tmp_path / "big.csv"
    big.write_bytes((FIX / "batch_b.csv").read_bytes() * 400)  # ~250 KB > 64 KB framing slack
    with TestClient(create_app(small), raise_server_exceptions=False) as c:
        ds = _dataset(c)
        with big.open("rb") as f:
            r = c.post(f"/api/v1/datasets/{ds}/uploads", files={"file": ("big.csv", f)}, headers=H)
    assert r.status_code == 413 and r.json()["type"] == "/errors/payload-too-large"


def test_small_file_over_cap_also_413(settings: Settings) -> None:
    """Under the framing slack, the streaming check in ingestion catches it — same response."""
    small = settings.model_copy(update={"max_upload_mb": 0})
    with TestClient(create_app(small), raise_server_exceptions=False) as c:
        r = _upload(c, _dataset(c), "batch_b.csv")
    assert r.status_code == 413


def test_load_sample_ingests_and_runs(client: TestClient, settings: Settings) -> None:
    settings.sample_dir.mkdir(parents=True)
    shutil.copy(FIX / "batch_b.csv", settings.sample_dir / "Year_2010-2011.csv")
    ds = _dataset(client, "Sample")
    r = client.post(f"/api/v1/datasets/{ds}/load-sample", headers=H)
    assert r.status_code == 202, r.text
    assert client.get(f"/api/v1/pipeline-runs/{r.json()['run_id']}").json()["status"] == (
        "succeeded"
    )
    repeat = client.post(f"/api/v1/datasets/{ds}/load-sample", headers=H)
    assert repeat.status_code == 200
    assert repeat.json() == {"run_id": None, "rerun_queued": False}
    runs = client.get("/api/v1/pipeline-runs", params={"dataset_id": ds}).json()["items"]
    assert len(runs) == 1


def test_repeat_sample_load_recovers_recorded_pending_work(
    client: TestClient, settings: Settings
) -> None:
    settings.sample_dir.mkdir(parents=True)
    sample = settings.sample_dir / "Year_2010-2011.csv"
    shutil.copy(FIX / "batch_b.csv", sample)
    ds = _dataset(client)
    app = client.app
    with sample.open("rb") as file:
        result = ingest_file(
            app.state.demo_ctx, app.state.engine, settings, uuid.UUID(ds), file, sample.name
        )
    assert result.created
    repeat = client.post(f"/api/v1/datasets/{ds}/load-sample", headers=H)
    assert repeat.status_code == 202
    run = client.get(f"/api/v1/pipeline-runs/{repeat.json()['run_id']}")
    assert run.json()["status"] == "succeeded"


def test_oversized_csv_header_returns_validation_error(client: TestClient) -> None:
    ds = _dataset(client)
    response = client.post(
        f"/api/v1/datasets/{ds}/uploads",
        files={"file": ("oversized.csv", b"x" * 16385 + b"\nvalue\n")},
        headers=H,
    )
    assert response.status_code == 422
    assert "header exceeds 16,384 characters" in response.json()["detail"]


def test_load_sample_without_files_explains_how_to_fetch(client: TestClient) -> None:
    ds = _dataset(client)
    r = client.post(f"/api/v1/datasets/{ds}/load-sample", headers=H)
    assert r.status_code == 404
    assert r.json()["type"] == "/errors/sample-data-missing"
    assert "fetch_sample_data" in r.json()["detail"]


def test_manual_run_request(client: TestClient) -> None:
    ds = _dataset(client)
    _upload(client, ds, "batch_b.csv")
    r = client.post(f"/api/v1/datasets/{ds}/pipeline-runs", headers=H)
    assert r.status_code == 202
    assert client.get(f"/api/v1/pipeline-runs/{r.json()['run_id']}").json()["status"] == (
        "succeeded"
    )
