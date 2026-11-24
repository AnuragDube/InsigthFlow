"""Shared test helpers: ingest the golden fixtures into Bronze."""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy.engine import Engine

from insightflow.core.context import OrgContext
from insightflow.core.settings import Settings
from insightflow.ingestion.service import ingest_file
from insightflow.metadata.bootstrap import ensure_demo_org
from insightflow.metadata.db import create_schema, make_engine, session_scope
from insightflow.metadata.repositories import DataSourceRepo
from insightflow.pipeline.silver import BatchInput
from insightflow.warehouse.paths import OrgPaths

FIX = Path(__file__).parent / "fixtures" / "ecommerce"


def setup_source(settings: Settings) -> tuple[Engine, OrgContext, uuid.UUID]:
    engine = make_engine(settings.database_url)
    create_schema(engine)
    with session_scope(engine) as s:
        ctx = ensure_demo_org(s, "demo")
        src = DataSourceRepo(s).create(ctx, name="Retail", domain="ecommerce", kind="file_upload")
    return engine, ctx, src.id


def ingest_fixtures(
    settings: Settings, engine: Engine, ctx: OrgContext, source_id: uuid.UUID,
    names: tuple[str | Path, ...] = ("batch_a.csv", "batch_b.csv"),
) -> list[BatchInput]:  # fmt: skip
    """Ingest fixture files (names relative to the fixtures dir, or full paths)."""
    paths = OrgPaths(settings.data_dir, ctx.org_id)
    inputs = []
    for order, name in enumerate(names):
        path = name if isinstance(name, Path) else FIX / name
        with path.open("rb") as f:
            ing = ingest_file(ctx, engine, settings, source_id, f, path.name).ingestion
        pq = paths.bronze_dir(source_id, ing.id) / "data.parquet"
        inputs.append(BatchInput(ingest_id=ing.id, parquet=pq, order=order))
    return inputs
