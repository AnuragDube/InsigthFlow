from __future__ import annotations

import hashlib
import io
import json
import uuid
from pathlib import Path

import duckdb
import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine

from insightflow.core.context import OrgContext
from insightflow.core.errors import PayloadTooLarge, ValidationFailed
from insightflow.core.settings import Settings
from insightflow.ingestion.service import ingest_file
from insightflow.metadata.bootstrap import ensure_demo_org
from insightflow.metadata.db import create_schema, make_engine, session_scope
from insightflow.metadata.models import AuditEvent, Ingestion
from insightflow.metadata.repositories import DataSourceRepo
from insightflow.warehouse.paths import OrgPaths

FIX = Path(__file__).parents[1] / "fixtures" / "ecommerce"


@pytest.fixture
def env(settings: Settings) -> tuple[Engine, OrgContext, uuid.UUID]:
    engine = make_engine(settings.database_url)
    create_schema(engine)
    with session_scope(engine) as s:
        ctx = ensure_demo_org(s, "demo")
        src = DataSourceRepo(s).create(ctx, name="Retail", domain="ecommerce", kind="file_upload")
    return engine, ctx, src.id


def _ingest(settings: Settings, env: tuple[Engine, OrgContext, uuid.UUID], name: str):  # type: ignore[no-untyped-def]
    engine, ctx, src_id = env
    with (FIX / name).open("rb") as f:
        return ingest_file(ctx, engine, settings, src_id, f, name)


def test_ingest_writes_immutable_bronze(settings: Settings, env) -> None:  # type: ignore[no-untyped-def]
    res = _ingest(settings, env, "batch_a.csv")
    assert res.created is True
    ing = res.ingestion
    assert ing.status == "stored" and ing.row_count == 14 and ing.is_active
    assert ing.sha256 == hashlib.sha256((FIX / "batch_a.csv").read_bytes()).hexdigest()
    d = OrgPaths(settings.data_dir, env[1].org_id).bronze_dir(env[2], ing.id)
    assert (d / "raw.csv").read_bytes() == (FIX / "batch_a.csv").read_bytes()
    manifest = json.loads((d / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest["row_count"] == 14 and manifest["sha256"] == ing.sha256


def test_bronze_parquet_is_all_text_with_line_order(settings: Settings, env) -> None:  # type: ignore[no-untyped-def]
    ing = _ingest(settings, env, "batch_a.csv").ingestion
    pq = OrgPaths(settings.data_dir, env[1].org_id).bronze_dir(env[2], ing.id) / "data.parquet"
    rows = duckdb.sql(
        f"select _row_number, Invoice, Quantity from read_parquet('{pq.as_posix()}') "
        "order by _row_number"
    ).fetchall()
    assert [r[0] for r in rows] == list(range(1, 15))
    assert rows[0][1] == "1001" and rows[8][1] == "A1007" and rows[11][2] == "x"
    described = duckdb.sql(f"describe select * from read_parquet('{pq.as_posix()}')").fetchall()
    types = {row[0]: row[1] for row in described}
    assert types["Quantity"] == "VARCHAR" and types["_ingest_id"] == "VARCHAR"


def test_reupload_same_bytes_returns_existing(settings: Settings, env) -> None:  # type: ignore[no-untyped-def]
    first = _ingest(settings, env, "batch_a.csv")
    second = _ingest(settings, env, "batch_a.csv")
    assert second.created is False
    assert second.ingestion.id == first.ingestion.id
    bronze_root = OrgPaths(settings.data_dir, env[1].org_id).bronze_root(env[2])
    assert len([p for p in bronze_root.iterdir() if p.is_dir()]) == 1


def test_wrong_headers_rejected_and_recorded(settings: Settings, env) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValidationFailed) as exc:
        _ingest(settings, env, "bad_headers.csv")
    assert "Country" in exc.value.detail
    engine, ctx, src_id = env
    with session_scope(engine) as s:
        ing = s.scalars(select(Ingestion)).one()
        assert ing.status == "rejected" and "Country" in (ing.rejection_reason or "")
        assert s.scalars(select(AuditEvent).where(AuditEvent.outcome == "error")).first()
    bronze_root = OrgPaths(settings.data_dir, ctx.org_id).bronze_root(src_id)
    assert not bronze_root.exists() or not any(p.is_dir() for p in bronze_root.iterdir())


def test_non_text_file_rejected(settings: Settings, env) -> None:  # type: ignore[no-untyped-def]
    engine, ctx, src_id = env
    with pytest.raises(ValidationFailed):
        ingest_file(ctx, engine, settings, src_id, io.BytesIO(b"\xff\xfe\x00\x01PK\x03"), "x.csv")


def test_size_cap_enforced(settings: Settings, env) -> None:  # type: ignore[no-untyped-def]
    tiny = settings.model_copy(update={"max_upload_mb": 0})
    with pytest.raises(PayloadTooLarge) as exc:
        _ingest(tiny, env, "batch_a.csv")
    assert "too large" in exc.value.detail


def test_successful_upload_is_audited(settings: Settings, env) -> None:  # type: ignore[no-untyped-def]
    ing = _ingest(settings, env, "batch_a.csv").ingestion
    with session_scope(env[0]) as s:
        ev = s.scalars(select(AuditEvent).where(AuditEvent.action == "dataset.upload")).one()
        assert ev.target_id == ing.id and ev.outcome == "success"
