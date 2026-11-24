"""Metadata tables (M1 subset of docs/DATA_ARCHITECTURE.md §7).

Tenant isolation is enforced in the schema itself: every tenant table carries ``org_id`` and
child rows reference parents through composite foreign keys that include ``org_id`` (and the
data source where relevant), so a row can never point at another org's or dataset's data.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


ACTIVE_RUN_STATUSES = ("queued", "running")


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    slug: Mapped[str] = mapped_column(String(63), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        CheckConstraint("status IN ('active','suspended','deleted')", name="ck_org_status"),
    )


class DataSource(Base):
    __tablename__ = "data_sources"
    org_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    domain: Mapped[str] = mapped_column(String(50))
    kind: Mapped[str] = mapped_column(String(20))
    contract_version: Mapped[str] = mapped_column(String(20))
    published_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    rerun_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_data_source_name"),
        CheckConstraint("kind IN ('file_upload','sample','connector')", name="ck_ds_kind"),
        # The published run must belong to the same org AND this data source.
        ForeignKeyConstraint(
            ["org_id", "id", "published_run_id"],
            ["pipeline_runs.org_id", "pipeline_runs.data_source_id", "pipeline_runs.id"],
            name="fk_ds_published_run",
            use_alter=True,
        ),
    )


class Ingestion(Base):
    __tablename__ = "ingestions"
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    data_source_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    original_name: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    row_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    storage_path: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(default=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        ForeignKeyConstraint(
            ["org_id", "data_source_id"],
            ["data_sources.org_id", "data_sources.id"],
            ondelete="CASCADE",
            name="fk_ingestion_source",
        ),
        UniqueConstraint("org_id", "data_source_id", "id", name="uq_ingestion_source_id"),
        CheckConstraint("status IN ('received','rejected','stored')", name="ck_ingestion_status"),
        CheckConstraint("size_bytes >= 0", name="ck_ingestion_size"),
        # Re-uploading identical bytes is idempotent; rejected uploads don't block a retry.
        Index(
            "uq_ingestion_bytes",
            "org_id",
            "data_source_id",
            "sha256",
            unique=True,
            sqlite_where=text("status = 'stored'"),
            postgresql_where=text("status = 'stored'"),
        ),
    )


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    data_source_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    trigger: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24))
    engine: Mapped[str] = mapped_column(String(16), default="duckdb")
    code_version: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        ForeignKeyConstraint(
            ["org_id", "data_source_id"],
            ["data_sources.org_id", "data_sources.id"],
            ondelete="CASCADE",
            name="fk_run_source",
        ),
        UniqueConstraint("org_id", "data_source_id", "id", name="uq_run_source_id"),
        CheckConstraint(
            "trigger IN ('upload','manual','schedule','sample','rerun')", name="ck_run_trigger"
        ),
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','blocked_by_quality')",
            name="ck_run_status",
        ),
        # Single writer per data source.
        Index(
            "uq_one_active_run",
            "org_id",
            "data_source_id",
            unique=True,
            sqlite_where=text("status IN ('queued','running')"),
            postgresql_where=text("status IN ('queued','running')"),
        ),
        Index("ix_runs_source_created", "org_id", "data_source_id", "created_at"),
    )


class PipelineRunInput(Base):
    __tablename__ = "pipeline_run_inputs"
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    ingestion_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    data_source_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    __table_args__ = (
        ForeignKeyConstraint(
            ["org_id", "data_source_id", "run_id"],
            ["pipeline_runs.org_id", "pipeline_runs.data_source_id", "pipeline_runs.id"],
            ondelete="CASCADE",
            name="fk_input_run",
        ),
        ForeignKeyConstraint(
            ["org_id", "data_source_id", "ingestion_id"],
            ["ingestions.org_id", "ingestions.data_source_id", "ingestions.id"],
            ondelete="CASCADE",
            name="fk_input_ingestion",
        ),
    )


class PipelineStageRun(Base):
    __tablename__ = "pipeline_stage_runs"
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    stage: Mapped[str] = mapped_column(String(20), primary_key=True)
    status: Mapped[str] = mapped_column(String(16))
    rows_in: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    rows_out: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    rows_quarantined: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    __table_args__ = (
        ForeignKeyConstraint(
            ["org_id", "run_id"],
            ["pipeline_runs.org_id", "pipeline_runs.id"],
            ondelete="CASCADE",
            name="fk_stage_run",
        ),
        CheckConstraint(
            "stage IN ('silver','silver_quality','gold','gold_quality','publish')",
            name="ck_stage_name",
        ),
    )


class QualityResult(Base):
    __tablename__ = "quality_results"
    org_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    stage: Mapped[str] = mapped_column(String(20), primary_key=True)
    rule_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    severity: Mapped[str] = mapped_column(String(16))
    passed: Mapped[bool]
    observed: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    threshold: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (
        ForeignKeyConstraint(
            ["org_id", "run_id"],
            ["pipeline_runs.org_id", "pipeline_runs.id"],
            ondelete="CASCADE",
            name="fk_quality_run",
        ),
        CheckConstraint("severity IN ('blocking','warning')", name="ck_quality_severity"),
    )


class AuditEvent(Base):
    """Append-only record of who did what. Never contains secrets or document contents."""

    __tablename__ = "audit_events"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("organizations.id"), nullable=True
    )
    actor_type: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    outcome: Mapped[str] = mapped_column(String(16))
    correlation_id: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        CheckConstraint("actor_type IN ('user','system','anonymous')", name="ck_audit_actor"),
        CheckConstraint("outcome IN ('success','denied','error')", name="ck_audit_outcome"),
        Index("ix_audit_org_time", "org_id", "occurred_at"),
    )
