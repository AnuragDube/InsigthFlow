from __future__ import annotations

import uuid

import duckdb
import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from insightflow.core.context import OrgContext
from insightflow.core.settings import Settings
from insightflow.domains.loader import DomainPack, load_domain_pack
from insightflow.metadata.db import session_scope
from insightflow.metadata.models import (
    DataSource,
    PipelineRun,
    PipelineRunInput,
    PipelineStageRun,
    QualityResult,
)
from insightflow.metadata.repositories import RunRepo
from insightflow.pipeline.gold import GOLD_TABLES
from insightflow.pipeline.service import (
    prune_old_runs,
    recover_interrupted_runs,
    request_run,
    run_pipeline,
)
from insightflow.warehouse.paths import OrgPaths
from pipeline_helpers import ingest_fixtures, setup_source

Env = tuple[Engine, OrgContext, uuid.UUID]


@pytest.fixture
def relaxed() -> DomainPack:
    """Fixtures deliberately quarantine 2/22 rows; relax that one gate for happy paths."""
    return load_domain_pack("ecommerce").with_threshold("quarantine_ratio", 0.2)


@pytest.fixture
def env(settings: Settings) -> Env:
    engine, ctx, src = setup_source(settings)
    ingest_fixtures(settings, engine, ctx, src)
    return engine, ctx, src


def _run(settings: Settings, env: Env, pack: DomainPack) -> PipelineRun:
    engine, ctx, src = env
    run = request_run(ctx, engine, src, trigger="manual")
    assert run is not None
    return run_pipeline(ctx, engine, settings, run.id, pack=pack)[-1]


def _source(env: Env) -> DataSource:
    engine, ctx, src = env
    with session_scope(engine) as s:
        ds = s.get(DataSource, (ctx.org_id, src))
        assert ds is not None
        return ds


def _gold_rows(settings: Settings, env: Env, run_id: uuid.UUID) -> dict[str, list[tuple]]:  # type: ignore[type-arg]
    db = OrgPaths(settings.data_dir, env[1].org_id).gold_db(env[2], run_id)
    con = duckdb.connect(str(db), read_only=True)
    try:
        return {t: con.execute(f"select * from {t} order by all").fetchall() for t in GOLD_TABLES}
    finally:
        con.close()


def test_happy_path_publishes_with_full_lineage(
    settings: Settings, env: Env, relaxed: DomainPack
) -> None:
    run = _run(settings, env, relaxed)
    assert run.status == "succeeded" and run.started_at and run.finished_at
    assert _source(env).published_run_id == run.id
    engine = env[0]
    with session_scope(engine) as s:
        stages = s.scalars(select(PipelineStageRun).where(PipelineStageRun.run_id == run.id)).all()
        assert {st.stage for st in stages} == {
            "silver", "silver_quality", "gold", "gold_quality", "publish",
        }  # fmt: skip
        assert all(st.status == "succeeded" and st.duration_ms is not None for st in stages)
        silver = next(st for st in stages if st.stage == "silver")
        assert (silver.rows_in, silver.rows_out, silver.rows_quarantined) == (22, 18, 2)
        n_quality = s.scalar(
            select(func.count()).select_from(QualityResult).where(QualityResult.run_id == run.id)
        )
        assert n_quality == len(relaxed.quality_rules)
        n_inputs = s.scalar(
            select(func.count())
            .select_from(PipelineRunInput)
            .where(PipelineRunInput.run_id == run.id)
        )
        assert n_inputs == 2


def test_rerun_on_same_inputs_is_identical(
    settings: Settings, env: Env, relaxed: DomainPack
) -> None:
    first = _run(settings, env, relaxed)
    second = _run(settings, env, relaxed)
    assert first.id != second.id
    assert _gold_rows(settings, env, first.id) == _gold_rows(settings, env, second.id)


def test_blocked_run_keeps_previous_publication(
    settings: Settings, env: Env, relaxed: DomainPack
) -> None:
    good = _run(settings, env, relaxed)
    blocked = _run(settings, env, load_domain_pack("ecommerce"))  # default 1% gate fails
    assert blocked.status == "blocked_by_quality"
    assert blocked.error_code == "quality_gate_failed"
    assert _source(env).published_run_id == good.id
    assert _gold_rows(settings, env, good.id)["fact_sales"]  # previous Gold still readable
    with session_scope(env[0]) as s:
        stages = {
            st.stage: st.status
            for st in s.scalars(
                select(PipelineStageRun).where(PipelineStageRun.run_id == blocked.id)
            )
        }
    assert stages == {"silver": "succeeded", "silver_quality": "failed"}


def test_no_active_batches_fails_cleanly(settings: Settings, relaxed: DomainPack) -> None:
    engine, ctx, src = setup_source(settings)
    run = request_run(ctx, engine, src, trigger="manual")
    assert run is not None
    done = run_pipeline(ctx, engine, settings, run.id, pack=relaxed)[-1]
    assert done.status == "failed" and done.error_code == "no_active_batches"


def test_request_during_active_run_coalesces_into_one_followup(
    settings: Settings, env: Env, relaxed: DomainPack
) -> None:
    engine, ctx, src = env
    active = request_run(ctx, engine, src, trigger="upload")
    assert active is not None
    assert request_run(ctx, engine, src, trigger="upload") is None  # marker set
    assert request_run(ctx, engine, src, trigger="upload") is None  # still one marker
    assert _source(env).rerun_requested_at is not None
    runs = run_pipeline(ctx, engine, settings, active.id, pack=relaxed)
    assert [r.status for r in runs] == ["succeeded", "succeeded"]
    assert runs[1].trigger == "rerun"
    ds = _source(env)
    assert ds.rerun_requested_at is None and ds.published_run_id == runs[1].id


def test_recovery_fails_interrupted_runs_and_requeues(
    settings: Settings, env: Env, relaxed: DomainPack
) -> None:
    engine, ctx, src = env
    with session_scope(engine) as s:
        crashed = RunRepo(s).create_queued(ctx, src, trigger="upload")
        crashed.status = "running"
    pending = recover_interrupted_runs(engine)
    with session_scope(engine) as s:
        again = RunRepo(s).get(ctx, crashed.id)
        assert again.status == "failed" and again.error_code == "interrupted"
    assert len(pending) == 1
    rctx, run_id = pending[0]
    assert rctx == ctx
    assert run_pipeline(rctx, engine, settings, run_id, pack=relaxed)[-1].status == "succeeded"


def test_prune_keeps_published_and_recent_runs(
    settings: Settings, env: Env, relaxed: DomainPack
) -> None:
    runs = [_run(settings, env, relaxed) for _ in range(4)]
    engine, ctx, src = env
    removed = prune_old_runs(ctx, engine, settings, src, keep=2)
    assert set(removed) == {runs[0].id, runs[1].id}
    paths = OrgPaths(settings.data_dir, ctx.org_id)
    assert not paths.gold_dir(src, runs[0].id).exists()
    assert paths.gold_db(src, runs[3].id).exists()
