"""HTTP request/response models. Kept separate from ORM models on purpose."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_ORM = ConfigDict(from_attributes=True)


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    domain: Literal["ecommerce"] = "ecommerce"


class DatasetOut(BaseModel):
    model_config = _ORM
    id: uuid.UUID
    name: str
    domain: str
    kind: str
    published_run_id: uuid.UUID | None
    rerun_requested_at: datetime | None
    created_at: datetime


class IngestionOut(BaseModel):
    model_config = _ORM
    id: uuid.UUID
    original_name: str
    sha256: str
    size_bytes: int
    row_count: int | None
    status: str
    is_active: bool
    created_at: datetime


class IngestionPatch(BaseModel):
    is_active: bool


class RunRequestOut(BaseModel):
    """``run_id`` is null when a run was already active and this request was coalesced."""

    run_id: uuid.UUID | None
    rerun_queued: bool


class UploadOut(RunRequestOut):
    ingestion: IngestionOut
    created: bool


class IngestionChangeOut(RunRequestOut):
    ingestion: IngestionOut


class StageOut(BaseModel):
    model_config = _ORM
    stage: str
    status: str
    rows_in: int | None
    rows_out: int | None
    rows_quarantined: int | None
    duration_ms: int | None


class RunOut(BaseModel):
    model_config = _ORM
    id: uuid.UUID
    data_source_id: uuid.UUID
    trigger: str
    status: str
    error_code: str | None
    code_version: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    stages: list[StageOut] = []


class QualityOut(BaseModel):
    model_config = _ORM
    rule_id: str
    stage: str
    severity: str
    passed: bool
    observed: float | None
    threshold: float | None
    description: str


class Page[T](BaseModel):
    items: list[T]
