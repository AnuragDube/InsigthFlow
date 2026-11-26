"""Pipeline run lifecycle: request, execute, publish, recover, prune.

Publication is a single metadata transaction that marks the run ``succeeded`` and points the data
source at it (``published_run_id``). Run outputs live in their own directories, so a failed or
blocked run can never change what readers see (DATA_ARCHITECTURE.md §4).
"""

from __future__ import annotations

import logging
import shutil
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

import duckdb
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from insightflow.core.context import OrgContext
from insightflow.core.errors import ConflictError
from insightflow.core.settings import Settings
from insightflow.domains.loader import DomainPack, load_domain_pack
from insightflow.metadata.db import session_scope
from insightflow.metadata.models import (
    ACTIVE_RUN_STATUSES,
    DataSource,
    PipelineRun,
    PipelineRunInput,
    PipelineStageRun,
    QualityResult,
)
from insightflow.metadata.repositories import AuditRepo, DataSourceRepo, IngestionRepo, RunRepo
from insightflow.pipeline.gold import build_gold
from insightflow.pipeline.silver import BatchInput, build_silver_in
from insightflow.quality.engine import (
    RuleResult,
    evaluate,
    gate_passed,
    open_gold_for_checks,
    register_stats,
)
from insightflow.warehouse.paths import OrgPaths

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


class _StageFailed(Exception):
    def __init__(self, status: str, error_code: str) -> None:
        super().__init__(error_code)
        self.status = status
        self.error_code = error_code


@dataclass
class _StageRecord:
    rows_in: int | None = None
    rows_out: int | None = None
    rows_quarantined: int | None = None
    extra: dict[str, object] = field(default_factory=dict)


# --------------------------------------------------------------------------- requesting runs


def request_run(
    ctx: OrgContext,
    engine: Engine,
    source_id: uuid.UUID,
    *,
    trigger: str,
    code_version: str = "dev",
    audit_rebuild: bool = False,
) -> PipelineRun | None:
    """Queue a run, or — if one is already active — leave the durable re-run marker set.

    One locked transaction: either a new run is created (and the marker cleared, because the new
    run will read every active batch), or the marker is set for the active run to pick up when it
    finishes. Returns the queued run, or ``None`` when the request was coalesced.
    """
    with session_scope(engine) as s:
        source = DataSourceRepo(s).lock(ctx, source_id)
        runs = RunRepo(s)
        if runs.active_for_source(ctx, source_id) is not None:
            source.rerun_requested_at = _now()
            run = None
        else:
            source.rerun_requested_at = None
            run = runs.create_queued(ctx, source_id, trigger=trigger, code_version=code_version)
        if audit_rebuild:
            AuditRepo(s).record(
                ctx,
                action="pipeline.rebuild_requested",
                target_type="dataset",
                target_id=source_id,
                details={
                    "run_id": str(run.id) if run is not None else None,
                    "coalesced": run is None,
                },
            )
        return run


def request_pending_run(
    ctx: OrgContext, engine: Engine, source_id: uuid.UUID, *, trigger: str, code_version: str
) -> tuple[PipelineRun | None, bool]:
    """Schedule work recorded by ingestion, preserving an active run's follow-up marker."""
    with session_scope(engine) as session:
        source = DataSourceRepo(session).lock(ctx, source_id)
        if source.rerun_requested_at is None:
            return None, False
        runs = RunRepo(session)
        if runs.active_for_source(ctx, source_id) is not None:
            return None, True
        source.rerun_requested_at = None
        return runs.create_queued(ctx, source_id, trigger=trigger, code_version=code_version), False


# --------------------------------------------------------------------------- executing runs


@contextmanager
def _stage(engine: Engine, ctx: OrgContext, run_id: uuid.UUID, name: str) -> Iterator[_StageRecord]:
    rec = _StageRecord()
    started, t0 = _now(), time.perf_counter()
    status = "failed"
    try:
        yield rec
        status = "succeeded"
    finally:
        with session_scope(engine) as s:
            s.add(
                PipelineStageRun(
                    org_id=ctx.org_id,
                    run_id=run_id,
                    stage=name,
                    status=status,
                    rows_in=rec.rows_in,
                    rows_out=rec.rows_out,
                    rows_quarantined=rec.rows_quarantined,
                    started_at=started,
                    finished_at=_now(),
                    duration_ms=int((time.perf_counter() - t0) * 1000),
                )
            )
        log.info("stage %s %s", name, status, extra={"run_id": str(run_id), "stage": name})


def _save_quality(
    engine: Engine, ctx: OrgContext, run_id: uuid.UUID, results: list[RuleResult]
) -> None:
    with session_scope(engine) as s:
        for r in results:
            s.add(
                QualityResult(
                    org_id=ctx.org_id,
                    run_id=run_id,
                    stage=r.stage,
                    rule_id=r.rule_id,
                    severity=r.severity,
                    passed=r.passed,
                    observed=None if r.observed is None else Decimal(str(r.observed)),
                    threshold=Decimal(str(r.threshold)),
                    description=r.description,
                )
            )


def _finish(
    s: Session,
    ctx: OrgContext,
    source_id: uuid.UUID,
    run_id: uuid.UUID,
    status: str,
    error_code: str | None = None,
) -> tuple[PipelineRun, uuid.UUID | None]:
    """Close the run; in the same locked transaction, turn a pending marker into the next run."""
    source = DataSourceRepo(s).lock(ctx, source_id)  # first statement: serializes with requests
    run = RunRepo(s).get(ctx, run_id)
    run.status = status
    run.finished_at = _now()
    run.error_code = error_code
    if status == "succeeded":
        source.published_run_id = run.id
    s.flush()  # the run is no longer active before a follow-up is inserted (single-writer index)
    AuditRepo(s).record(
        ctx,
        action="pipeline.run",
        actor_type="system",
        outcome="success" if status == "succeeded" else "error",
        target_type="pipeline_run",
        target_id=run.id,
        details={"status": status, "error_code": error_code},
    )
    if source.rerun_requested_at is None:
        return run, None
    source.rerun_requested_at = None
    follow_up = RunRepo(s).create_queued(
        ctx, source.id, trigger="rerun", code_version=run.code_version
    )
    return run, follow_up.id


def _fail_safely(ctx: OrgContext, engine: Engine, run_id: uuid.UUID) -> uuid.UUID | None:
    """Best effort: never leave a run queued/running after an unexpected error."""
    try:
        with session_scope(engine) as s:
            run = RunRepo(s).get(ctx, run_id)
            if run.status not in ACTIVE_RUN_STATUSES:
                return None
            source_id = run.data_source_id
        with session_scope(engine) as s:
            return _finish(s, ctx, source_id, run_id, "failed", "internal_error")[1]
    except Exception:
        log.exception(
            "could not mark run failed; the startup sweep will", extra={"run_id": str(run_id)}
        )
        return None


def _execute(
    ctx: OrgContext,
    engine: Engine,
    settings: Settings,
    run_id: uuid.UUID,
    pack: DomainPack | None,
) -> tuple[PipelineRun, uuid.UUID | None]:
    paths = OrgPaths(settings.data_dir, ctx.org_id)
    with session_scope(engine) as s:
        peek = RunRepo(s).get(ctx, run_id)
        source_id = peek.data_source_id
    with session_scope(engine) as s:
        source = DataSourceRepo(s).lock(ctx, source_id)  # first statement of the transaction
        run = RunRepo(s).get(ctx, run_id)
        if run.status != "queued":
            raise ConflictError("Only queued runs can be executed.")
        pack = pack or load_domain_pack(source.domain)
        batches = IngestionRepo(s).list_active(ctx, source.id)
        run.status, run.started_at = "running", _now()
        for b in batches:
            s.add(
                PipelineRunInput(
                    org_id=ctx.org_id, run_id=run.id, ingestion_id=b.id, data_source_id=source.id
                )
            )
        inputs = [
            BatchInput(b.id, paths.bronze_dir(source_id, b.id) / "data.parquet", order)
            for order, b in enumerate(batches)
        ]

    status, error_code = "succeeded", None
    try:
        if not inputs:
            raise _StageFailed("failed", "no_active_batches")
        silver_dir = paths.silver_dir(source_id, run_id)
        gold_dir = paths.gold_dir(source_id, run_id)
        con = duckdb.connect()
        try:
            con.execute(f"SET memory_limit = '{settings.duckdb_memory_limit}'")
            con.execute(f"SET threads = {int(settings.duckdb_threads)}")
            with _stage(engine, ctx, run_id, "silver") as rec:
                stats = build_silver_in(
                    con, inputs, silver_dir, paths.quarantine_dir(source_id, run_id), pack
                )
                rec.rows_in, rec.rows_out = stats.rows_in, stats.rows_out
                rec.rows_quarantined = stats.quarantined
            with _stage(engine, ctx, run_id, "silver_quality"):
                register_stats(con, stats)
                results = evaluate(con, pack.quality_rules, "silver")
                _save_quality(engine, ctx, run_id, results)
                if not gate_passed(results):
                    raise _StageFailed("blocked_by_quality", "quality_gate_failed")
        finally:
            con.close()
        silver_parquet = silver_dir / "order_lines.parquet"
        with _stage(engine, ctx, run_id, "gold") as rec:
            gold = build_gold(
                silver_parquet,
                gold_dir,
                pack,
                memory_limit=settings.duckdb_memory_limit,
                threads=settings.duckdb_threads,
            )
            rec.rows_in, rec.rows_out = stats.rows_out, gold.table_rows["fact_sales"]
        with _stage(engine, ctx, run_id, "gold_quality"):
            check = open_gold_for_checks(gold_dir / "gold.duckdb", silver_parquet)
            try:
                results = evaluate(check, pack.quality_rules, "gold")
            finally:
                check.close()
            _save_quality(engine, ctx, run_id, results)
            if not gate_passed(results):
                raise _StageFailed("blocked_by_quality", "quality_gate_failed")
    except _StageFailed as exc:
        status, error_code = exc.status, exc.error_code
    except Exception:
        log.exception("pipeline run failed", extra={"run_id": str(run_id)})
        status, error_code = "failed", "internal_error"

    if status == "succeeded":
        with _stage(engine, ctx, run_id, "publish"), session_scope(engine) as s:
            return _finish(s, ctx, source_id, run_id, "succeeded")
    with session_scope(engine) as s:
        return _finish(s, ctx, source_id, run_id, status, error_code)


def run_pipeline(
    ctx: OrgContext,
    engine: Engine,
    settings: Settings,
    run_id: uuid.UUID,
    *,
    pack: DomainPack | None = None,
) -> list[PipelineRun]:
    """Execute a queued run, then any coalesced follow-up runs. Returns all runs executed."""
    executed: list[PipelineRun] = []
    next_id: uuid.UUID | None = run_id
    while next_id is not None:
        current = next_id
        try:
            run, next_id = _execute(ctx, engine, settings, current, pack)
        except ConflictError:
            raise  # not queued (e.g. already executed): nothing to clean up
        except Exception:
            log.exception("pipeline run crashed outside its stages", extra={"run_id": str(current)})
            next_id = _fail_safely(ctx, engine, current)
            with session_scope(engine) as s:
                run = RunRepo(s).get(ctx, current)
        executed.append(run)
    return executed


# --------------------------------------------------------------------------- recovery & pruning


def recover_interrupted_runs(engine: Engine) -> list[tuple[OrgContext, uuid.UUID]]:
    """Startup sweep (single process): fail runs a crash left active, then queue their re-runs.

    This is a system operation across orgs; each re-queued run stays bound to its own org.
    """
    pending: list[tuple[OrgContext, uuid.UUID]] = []
    with session_scope(engine) as s:
        stuck = s.scalars(
            select(PipelineRun).where(PipelineRun.status.in_(ACTIVE_RUN_STATUSES))
        ).all()
        for run in stuck:
            run.status, run.finished_at, run.error_code = "failed", _now(), "interrupted"
            source = s.get(DataSource, (run.org_id, run.data_source_id))
            if source is not None:
                source.rerun_requested_at = source.rerun_requested_at or _now()
        s.flush()
        sources = s.scalars(select(DataSource).where(DataSource.rerun_requested_at.is_not(None)))
        for source in sources.all():
            ctx = OrgContext(source.org_id)
            source.rerun_requested_at = None
            run = RunRepo(s).create_queued(ctx, source.id, trigger="rerun")
            pending.append((ctx, run.id))
    if stuck:
        log.warning("recovered %d interrupted pipeline run(s)", len(stuck))
    return pending


def prune_old_runs(
    ctx: OrgContext, engine: Engine, settings: Settings, source_id: uuid.UUID, *, keep: int = 2
) -> list[uuid.UUID]:
    """Delete outputs of old runs, keeping the published run and the ``keep`` most recent.

    Deletion failures (e.g. a file still open on Windows) are logged and retried next time.
    """
    with session_scope(engine) as s:
        source = DataSourceRepo(s).get(ctx, source_id)
        runs = RunRepo(s).list_all(ctx, source_id, limit=10_000)
        protected = {r.id for r in runs[:keep]} | {source.published_run_id}
        protected |= {r.id for r in runs if r.status in ACTIVE_RUN_STATUSES}
        candidates = [r.id for r in runs if r.id not in protected]
    paths = OrgPaths(settings.data_dir, ctx.org_id)
    removed = []
    for run_id in candidates:
        dirs = [
            paths.silver_dir(source_id, run_id),
            paths.quarantine_dir(source_id, run_id),
            paths.gold_dir(source_id, run_id),
        ]
        if not any(d.exists() for d in dirs):
            continue
        try:
            for d in dirs:
                if d.exists():
                    shutil.rmtree(d)
            removed.append(run_id)
        except OSError:
            log.warning("could not prune run %s; will retry later", run_id, exc_info=True)
    return removed
