"""Org-scoped data access. Every method takes an ``OrgContext`` first and filters by it.

There is deliberately no way to query tenant tables without an org: a forgotten filter is the
most common cause of cross-tenant leaks.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from insightflow.core.context import OrgContext
from insightflow.core.errors import ConflictError, NotFoundError
from insightflow.core.ids import new_id
from insightflow.core.logging import correlation_id
from insightflow.metadata.models import (
    ACTIVE_RUN_STATUSES,
    AuditEvent,
    DataSource,
    Ingestion,
    Organization,
    PipelineRun,
    PipelineStageRun,
    QualityResult,
)


def _flush_or_conflict(session: Session, message: str) -> None:
    try:
        session.flush()
    except IntegrityError as exc:
        raise ConflictError(message) from exc


class DataSourceRepo:
    def __init__(self, session: Session) -> None:
        self.s = session

    def create(
        self, ctx: OrgContext, *, name: str, domain: str, kind: str, contract_version: str = "1"
    ) -> DataSource:
        ds = DataSource(
            org_id=ctx.org_id,
            id=new_id(),
            name=name,
            domain=domain,
            kind=kind,
            contract_version=contract_version,
        )
        self.s.add(ds)
        _flush_or_conflict(self.s, f"A dataset named '{name}' already exists.")
        return ds

    def get(self, ctx: OrgContext, source_id: uuid.UUID) -> DataSource:
        ds = self.s.get(DataSource, (ctx.org_id, source_id))
        if ds is None:  # also the answer for another org's id: don't reveal existence
            raise NotFoundError("Dataset not found.")
        return ds

    def lock(self, ctx: OrgContext, source_id: uuid.UUID) -> DataSource:
        """Serialize pipeline-state changes for one data source.

        Must be the FIRST statement of the transaction. A no-op UPDATE takes the database write
        lock on SQLite (others wait up to busy_timeout) and a row lock on PostgreSQL, so
        check-then-act sequences ("is a run active? then set the marker") cannot interleave.
        """
        result = self.s.execute(
            update(DataSource)
            .where(DataSource.org_id == ctx.org_id, DataSource.id == source_id)
            .values(rerun_requested_at=DataSource.rerun_requested_at)
            .execution_options(synchronize_session=False)
        )
        if getattr(result, "rowcount", 1) == 0:
            raise NotFoundError("Dataset not found.")
        return self.get(ctx, source_id)

    def list_all(self, ctx: OrgContext) -> list[DataSource]:
        q = select(DataSource).where(DataSource.org_id == ctx.org_id).order_by(DataSource.name)
        return list(self.s.scalars(q))

    def with_rerun_requested(self, ctx: OrgContext) -> list[DataSource]:
        q = select(DataSource).where(
            DataSource.org_id == ctx.org_id, DataSource.rerun_requested_at.is_not(None)
        )
        return list(self.s.scalars(q))


class IngestionRepo:
    def __init__(self, session: Session) -> None:
        self.s = session

    def add(
        self,
        ctx: OrgContext,
        source_id: uuid.UUID,
        *,
        original_name: str,
        sha256: str,
        size_bytes: int,
        status: str,
        ingestion_id: uuid.UUID | None = None,
        row_count: int | None = None,
        storage_path: str = "",
        rejection_reason: str | None = None,
    ) -> Ingestion:
        ing = Ingestion(
            org_id=ctx.org_id,
            id=ingestion_id or new_id(),
            data_source_id=source_id,
            original_name=original_name,
            sha256=sha256,
            size_bytes=size_bytes,
            status=status,
            row_count=row_count,
            storage_path=storage_path,
            rejection_reason=rejection_reason,
            is_active=status == "stored",
        )
        self.s.add(ing)
        _flush_or_conflict(self.s, "This file was already ingested for this dataset.")
        return ing

    def get(self, ctx: OrgContext, source_id: uuid.UUID, ingestion_id: uuid.UUID) -> Ingestion:
        ing = self.s.get(Ingestion, (ctx.org_id, ingestion_id))
        if ing is None or ing.data_source_id != source_id:
            raise NotFoundError("Ingestion not found.")
        return ing

    def lock_workspace_storage(self, ctx: OrgContext) -> None:
        """Serialize storage accounting by workspace on SQLite and PostgreSQL."""
        self.s.execute(
            update(Organization)
            .where(Organization.id == ctx.org_id)
            .values(status=Organization.status)
        )

    def stored_bytes(self, ctx: OrgContext) -> int:
        return (
            self.s.scalar(
                select(func.coalesce(func.sum(Ingestion.size_bytes), 0)).where(
                    Ingestion.org_id == ctx.org_id, Ingestion.status == "stored"
                )
            )
            or 0
        )

    def find_stored_by_sha(
        self, ctx: OrgContext, source_id: uuid.UUID, sha256: str
    ) -> Ingestion | None:
        q = select(Ingestion).where(
            Ingestion.org_id == ctx.org_id,
            Ingestion.data_source_id == source_id,
            Ingestion.sha256 == sha256,
            Ingestion.status == "stored",
        )
        return self.s.scalars(q).first()

    def list_all(self, ctx: OrgContext, source_id: uuid.UUID) -> list[Ingestion]:
        q = (
            select(Ingestion)
            .where(Ingestion.org_id == ctx.org_id, Ingestion.data_source_id == source_id)
            .order_by(Ingestion.created_at, Ingestion.id)
        )
        return list(self.s.scalars(q))

    def set_active(
        self, ctx: OrgContext, source_id: uuid.UUID, ingestion_id: uuid.UUID, active: bool
    ) -> Ingestion:
        ing = self.get(ctx, source_id, ingestion_id)
        if ing.status != "stored":
            raise ConflictError("Only stored batches can be activated or deactivated.")
        ing.is_active = active
        return ing

    def list_active(self, ctx: OrgContext, source_id: uuid.UUID) -> list[Ingestion]:
        return [i for i in self.list_all(ctx, source_id) if i.status == "stored" and i.is_active]


class RunRepo:
    def __init__(self, session: Session) -> None:
        self.s = session

    def create_queued(
        self, ctx: OrgContext, source_id: uuid.UUID, *, trigger: str, code_version: str = "dev"
    ) -> PipelineRun:
        run = PipelineRun(
            org_id=ctx.org_id,
            id=new_id(),
            data_source_id=source_id,
            trigger=trigger,
            status="queued",
            code_version=code_version,
        )
        self.s.add(run)
        _flush_or_conflict(self.s, "A pipeline run is already active for this dataset.")
        return run

    def get(self, ctx: OrgContext, run_id: uuid.UUID) -> PipelineRun:
        run = self.s.get(PipelineRun, (ctx.org_id, run_id))
        if run is None:
            raise NotFoundError("Pipeline run not found.")
        return run

    def active_for_source(self, ctx: OrgContext, source_id: uuid.UUID) -> PipelineRun | None:
        q = select(PipelineRun).where(
            PipelineRun.org_id == ctx.org_id,
            PipelineRun.data_source_id == source_id,
            PipelineRun.status.in_(ACTIVE_RUN_STATUSES),
        )
        return self.s.scalars(q).first()

    def list_all(self, ctx: OrgContext, source_id: uuid.UUID, limit: int = 50) -> list[PipelineRun]:
        q = (
            select(PipelineRun)
            .where(PipelineRun.org_id == ctx.org_id, PipelineRun.data_source_id == source_id)
            .order_by(PipelineRun.created_at.desc(), PipelineRun.id.desc())
            .limit(limit)
        )
        return list(self.s.scalars(q))

    def stages(self, ctx: OrgContext, run_id: uuid.UUID) -> list[PipelineStageRun]:
        q = (
            select(PipelineStageRun)
            .where(PipelineStageRun.org_id == ctx.org_id, PipelineStageRun.run_id == run_id)
            .order_by(PipelineStageRun.started_at)
        )
        return list(self.s.scalars(q))

    def quality(self, ctx: OrgContext, run_id: uuid.UUID) -> list[QualityResult]:
        q = (
            select(QualityResult)
            .where(QualityResult.org_id == ctx.org_id, QualityResult.run_id == run_id)
            .order_by(QualityResult.stage.desc(), QualityResult.rule_id)
        )
        return list(self.s.scalars(q))


class AuditRepo:
    def __init__(self, session: Session) -> None:
        self.s = session

    def record(
        self,
        ctx: OrgContext | None,
        *,
        action: str,
        outcome: str = "success",
        actor_type: str | None = None,
        target_type: str | None = None,
        target_id: uuid.UUID | None = None,
        details: dict[str, Any] | None = None,
        at: datetime | None = None,
    ) -> AuditEvent:
        actor_ref = ctx.audit_actor_ref if ctx else None
        if actor_type is None:
            actor_type = "user" if actor_ref else "anonymous"
        event_details = dict(details or {})
        if actor_type == "user" and actor_ref:
            event_details["actor_ref"] = actor_ref
        ev = AuditEvent(
            id=new_id(),
            org_id=ctx.org_id if ctx else None,
            actor_type=actor_type,
            action=action,
            outcome=outcome,
            target_type=target_type,
            target_id=target_id,
            correlation_id=correlation_id.get(),
            details=event_details,
        )
        if at is not None:
            ev.occurred_at = at
        self.s.add(ev)
        return ev
