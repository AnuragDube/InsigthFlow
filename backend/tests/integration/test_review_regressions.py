"""Regression tests for findings from the M1 final review (each failed before its fix)."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from insightflow.api.app import create_app
from insightflow.core.context import OrgContext
from insightflow.core.settings import Settings
from insightflow.domains.loader import load_domain_pack
from insightflow.metadata.db import session_scope
from insightflow.metadata.models import DataSource
from insightflow.metadata.repositories import RunRepo
from insightflow.pipeline import service
from insightflow.pipeline.gold import build_gold
from insightflow.pipeline.service import recover_interrupted_runs, request_run, run_pipeline
from insightflow.pipeline.silver import build_silver
from pipeline_helpers import ingest_fixtures, setup_source

HEADER = "Invoice,StockCode,Description,Quantity,InvoiceDate,Price,Customer ID,Country\n"


def _source(engine: Engine, ctx: OrgContext, src: uuid.UUID) -> DataSource:
    with session_scope(engine) as s:
        ds = s.get(DataSource, (ctx.org_id, src))
        assert ds is not None
        return ds


# --- Finding 1: lost re-run requests / stuck runs -------------------------------------------


def test_upload_alone_leaves_durable_pending_work(settings: Settings) -> None:
    """A crash between storing a batch and requesting a run must not strand the batch."""
    engine, ctx, src = setup_source(settings)
    ingest_fixtures(settings, engine, ctx, src, names=("batch_b.csv",))
    assert _source(engine, ctx, src).rerun_requested_at is not None
    pending = recover_interrupted_runs(engine)
    assert [run_id for _, run_id in pending]


def test_request_racing_with_run_finish_is_not_lost(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, ctx, src = setup_source(settings)
    ingest_fixtures(settings, engine, ctx, src, names=("batch_b.csv",))
    active = request_run(ctx, engine, src, trigger="upload")
    assert active is not None

    checked, proceed = threading.Event(), threading.Event()
    original = RunRepo.active_for_source

    def paused(self: RunRepo, c: OrgContext, s: uuid.UUID):  # type: ignore[no-untyped-def]
        result = original(self, c, s)
        if not checked.is_set():
            checked.set()
            proceed.wait(timeout=10)
        return result

    monkeypatch.setattr(RunRepo, "active_for_source", paused)
    requester = threading.Thread(
        target=request_run, args=(ctx, engine, src), kwargs={"trigger": "manual"}
    )
    requester.start()
    assert checked.wait(timeout=10)
    runs: list[object] = []
    finisher = threading.Thread(
        target=lambda: runs.extend(run_pipeline(ctx, engine, settings, active.id))
    )
    finisher.start()
    finisher.join(timeout=3)  # with correct locking the finisher waits for the requester
    proceed.set()
    requester.join(timeout=10)
    finisher.join(timeout=30)

    ds = _source(engine, ctx, src)
    with session_scope(engine) as s:
        still_active = RunRepo(s).active_for_source(ctx, src)
    assert ds.rerun_requested_at is None or still_active is not None, "re-run request lost"


def test_setup_failure_does_not_leave_run_stuck(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, ctx, src = setup_source(settings)
    ingest_fixtures(settings, engine, ctx, src, names=("batch_b.csv",))
    run = request_run(ctx, engine, src, trigger="manual")
    assert run is not None

    def broken(_: str) -> None:
        raise RuntimeError("pack failed to load")

    monkeypatch.setattr(service, "load_domain_pack", broken)
    run_pipeline(ctx, engine, settings, run.id)
    with session_scope(engine) as s:
        assert RunRepo(s).get(ctx, run.id).status == "failed"
    monkeypatch.undo()
    assert request_run(ctx, engine, src, trigger="manual") is not None  # not blocked forever


# --- Finding 2: size limit enforced while streaming ------------------------------------------


@pytest.fixture
def tiny_client(settings: Settings) -> Iterator[TestClient]:
    small = settings.model_copy(update={"max_upload_mb": 0})
    with TestClient(create_app(small), raise_server_exceptions=False) as c:
        yield c


def test_chunked_upload_over_cap_is_413(tiny_client: TestClient) -> None:
    def body() -> Iterator[bytes]:
        for _ in range(64):
            yield b"x" * 4096  # 256 KB, no Content-Length (chunked)

    r = tiny_client.post(
        "/api/v1/datasets/00000000-0000-0000-0000-000000000000/uploads",
        content=body(),
        headers={"X-InsightFlow-Client": "web", "Content-Type": "multipart/form-data; boundary=x"},
    )
    assert r.status_code == 413 and r.json()["type"] == "/errors/payload-too-large"


# --- Finding 3 & 7: strict casts and case-insensitive prefixes --------------------------------


@pytest.fixture
def odd_silver(settings: Settings, tmp_path: Path) -> Path:
    csv = tmp_path / "odd.csv"
    csv.write_text(
        HEADER
        + "1,22633,A,1.6,2010-12-01 08:00:00,1.85,1,UK\n"  # decimal quantity
        + "2,22633,A,1e3,2010-12-01 08:00:00,1.85,1,UK\n"  # scientific quantity
        + "3,22633,A,1,2010-12-01T08:00:00Z,1.85,1,UK\n"  # timezone marker
        + "4,22633,A,1,2010-12-01 08:00:00,1e1,1,UK\n"  # scientific price
        + "c5,22633,A,-1,2010-12-01 09:00:00,1.85,1,UK\n"  # lowercase cancellation
        + "6,22633,A,2,2010-12-01 10:00:00,1.85,1,UK\n",
        "utf-8",
    )
    engine, ctx, src = setup_source(settings)
    inputs = ingest_fixtures(settings, engine, ctx, src, names=(csv,))
    build_silver(inputs, tmp_path / "s", tmp_path / "q", load_domain_pack("ecommerce"))
    return tmp_path


def test_non_integer_quantities_and_zoned_timestamps_are_quarantined(odd_silver: Path) -> None:
    path = (odd_silver / "q" / "rejected.parquet").as_posix()
    rejected = duckdb.sql(
        f"select raw_invoice, reason_code from read_parquet('{path}') order by 1"
    ).fetchall()
    assert rejected == [
        ("1", "bad_quantity"),
        ("2", "bad_quantity"),
        ("3", "bad_timestamp"),
        ("4", "bad_price"),
    ]


def test_lowercase_cancellation_prefix_is_a_cancellation(odd_silver: Path) -> None:
    path = (odd_silver / "s" / "order_lines.parquet").as_posix()
    rows = duckdb.sql(
        f"select invoice_no, is_cancellation from read_parquet('{path}') order by 1"
    ).fetchall()
    assert rows == [("6", False), ("C5", True)]


# --- Finding 4: deterministic dim_product tie-break -------------------------------------------


def test_dim_product_description_tie_break_is_deterministic(
    settings: Settings, tmp_path: Path
) -> None:
    csv = tmp_path / "ties.csv"
    lines = [f"{i},22633,DESC {chr(90 - i)},1,2010-12-01 08:00:00,1.85,1,UK" for i in range(12)]
    csv.write_text(HEADER + "\n".join(lines) + "\n", "utf-8")
    engine, ctx, src = setup_source(settings)
    inputs = ingest_fixtures(settings, engine, ctx, src, names=(csv,))
    pack = load_domain_pack("ecommerce")
    build_silver(inputs, tmp_path / "s", tmp_path / "q", pack)
    seen = set()
    for i in range(6):
        build_gold(tmp_path / "s" / "order_lines.parquet", tmp_path / f"g{i}", pack)
        con = duckdb.connect(str(tmp_path / f"g{i}" / "gold.duckdb"), read_only=True)
        seen.add(con.execute("select description from dim_product").fetchone())
        con.close()
    assert seen == {("DESC O",)}  # latest timestamp tie -> alphabetically first
