"""The Gold reader is a security boundary: generated SQL will run on these connections."""

from __future__ import annotations

import uuid

import duckdb
import pytest
from pydantic import ValidationError
from sqlalchemy.engine import Engine

from insightflow.core.context import OrgContext
from insightflow.core.errors import NoPublishedData
from insightflow.core.settings import Settings
from insightflow.domains.loader import load_domain_pack
from insightflow.pipeline.service import request_run, run_pipeline
from insightflow.warehouse.engine import open_gold
from pipeline_helpers import FIX, ingest_fixtures, setup_source

Env = tuple[Engine, OrgContext, uuid.UUID]


@pytest.fixture
def published(settings: Settings) -> Env:
    engine, ctx, src = setup_source(settings)
    ingest_fixtures(settings, engine, ctx, src)
    run = request_run(ctx, engine, src, trigger="manual")
    assert run is not None
    pack = load_domain_pack("ecommerce").with_threshold("quarantine_ratio", 0.2)
    assert run_pipeline(ctx, engine, settings, run.id, pack=pack)[-1].status == "succeeded"
    return engine, ctx, src


def test_reads_published_gold(settings: Settings, published: Env) -> None:
    engine, ctx, src = published
    con = open_gold(ctx, engine, settings, src)
    assert con.execute("select count(*) from fact_sales").fetchone() == (10,)


@pytest.mark.parametrize(
    "sql",
    [
        f"select * from read_csv('{(FIX / 'batch_a.csv').as_posix()}')",
        f"select * from read_parquet('{(FIX / 'batch_a.csv').as_posix()}')",
        "copy fact_sales to 'out.csv'",
        "attach ':memory:' as other",
        "install httpfs",
        "load httpfs",
        "set enable_external_access = true",
        "set lock_configuration = false",
        "insert into fact_sales select * from fact_sales",
        "create table x as select 1",
        "drop table fact_sales",
    ],
)
def test_sandbox_blocks_escape_attempts(settings: Settings, published: Env, sql: str) -> None:
    engine, ctx, src = published
    con = open_gold(ctx, engine, settings, src)
    with pytest.raises(duckdb.Error):
        con.execute(sql)


def test_two_readers_in_one_process(settings: Settings, published: Env) -> None:
    engine, ctx, src = published
    a = open_gold(ctx, engine, settings, src)
    b = open_gold(ctx, engine, settings, src)
    assert a.execute("select 1").fetchone() == b.execute("select 1").fetchone()


def test_no_published_data_is_a_clear_error(settings: Settings) -> None:
    engine, ctx, src = setup_source(settings)
    with pytest.raises(NoPublishedData):
        open_gold(ctx, engine, settings, src)


@pytest.mark.parametrize("bad", ["1GB'; drop", "lots", "-1GB"])
def test_memory_limit_setting_is_validated(bad: str) -> None:
    with pytest.raises(ValidationError):
        Settings(duckdb_memory_limit=bad)
