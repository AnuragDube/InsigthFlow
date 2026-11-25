from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Response, UploadFile, status
from sqlalchemy.engine import Engine

from insightflow.api.background import run_in_background
from insightflow.api.deps import get_editor_context, get_engine, get_org_context, get_settings_dep
from insightflow.api.schemas import (
    DatasetCreate,
    DatasetOut,
    IngestionChangeOut,
    IngestionOut,
    IngestionPatch,
    Page,
    RunRequestOut,
    UploadOut,
)
from insightflow.core.context import OrgContext
from insightflow.core.errors import AppError
from insightflow.core.settings import Settings
from insightflow.ingestion.service import ingest_file
from insightflow.metadata.db import session_scope
from insightflow.metadata.repositories import AuditRepo, DataSourceRepo, IngestionRepo
from insightflow.pipeline.service import request_run

router = APIRouter(prefix="/api/v1/datasets", tags=["datasets"])

Ctx = Annotated[OrgContext, Depends(get_org_context)]
EditorCtx = Annotated[OrgContext, Depends(get_editor_context)]
Eng = Annotated[Engine, Depends(get_engine)]
Cfg = Annotated[Settings, Depends(get_settings_dep)]


class SampleDataMissing(AppError):
    status, type_slug, title = 404, "sample-data-missing", "Sample data not found"


def _queue(
    ctx: OrgContext,
    engine: Engine,
    settings: Settings,
    tasks: BackgroundTasks,
    source_id: uuid.UUID,
    trigger: str,
) -> RunRequestOut:
    run = request_run(ctx, engine, source_id, trigger=trigger, code_version=settings.code_version)
    if run is None:
        return RunRequestOut(run_id=None, rerun_queued=True)
    tasks.add_task(run_in_background, ctx, engine, settings, run.id)
    return RunRequestOut(run_id=run.id, rerun_queued=False)


@router.get("")
def list_datasets(ctx: Ctx, engine: Eng) -> Page[DatasetOut]:
    with session_scope(engine) as s:
        return Page(items=[DatasetOut.model_validate(d) for d in DataSourceRepo(s).list_all(ctx)])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_dataset(body: DatasetCreate, ctx: EditorCtx, engine: Eng) -> DatasetOut:
    with session_scope(engine) as s:
        ds = DataSourceRepo(s).create(ctx, name=body.name, domain=body.domain, kind="file_upload")
        AuditRepo(s).record(ctx, action="dataset.create", target_type="dataset", target_id=ds.id)
        return DatasetOut.model_validate(ds)


@router.get("/{dataset_id}/ingestions")
def list_ingestions(dataset_id: uuid.UUID, ctx: Ctx, engine: Eng) -> Page[IngestionOut]:
    with session_scope(engine) as s:
        DataSourceRepo(s).get(ctx, dataset_id)
        items = IngestionRepo(s).list_all(ctx, dataset_id)
        return Page(items=[IngestionOut.model_validate(i) for i in items if i.status == "stored"])


@router.post("/{dataset_id}/uploads", status_code=status.HTTP_201_CREATED)
def upload(
    dataset_id: uuid.UUID,
    file: Annotated[UploadFile, File()],
    response: Response,
    tasks: BackgroundTasks,
    ctx: EditorCtx,
    engine: Eng,
    settings: Cfg,
) -> UploadOut:
    result = ingest_file(ctx, engine, settings, dataset_id, file.file, file.filename or "")
    ing = IngestionOut.model_validate(result.ingestion)
    if not result.created:
        response.status_code = status.HTTP_200_OK
        return UploadOut(ingestion=ing, created=False, run_id=None, rerun_queued=False)
    queued = _queue(ctx, engine, settings, tasks, dataset_id, "upload")
    return UploadOut(ingestion=ing, created=True, **queued.model_dump())


@router.post("/{dataset_id}/load-sample", status_code=status.HTTP_202_ACCEPTED)
def load_sample(
    dataset_id: uuid.UUID, tasks: BackgroundTasks, ctx: EditorCtx, engine: Eng, settings: Cfg
) -> RunRequestOut:
    with session_scope(engine) as session:
        DataSourceRepo(session).get(ctx, dataset_id)
    files = sorted(settings.sample_dir.glob("*.csv")) if settings.sample_dir.is_dir() else []
    if not files:
        raise SampleDataMissing(
            "Sample data is not downloaded. Run `uv run python scripts/fetch_sample_data.py` "
            "and try again."
        )
    for path in files:
        with path.open("rb") as f:
            ingest_file(ctx, engine, settings, dataset_id, f, path.name)
    return _queue(ctx, engine, settings, tasks, dataset_id, "sample")


@router.patch("/{dataset_id}/ingestions/{ingestion_id}")
def change_ingestion(
    dataset_id: uuid.UUID,
    ingestion_id: uuid.UUID,
    body: IngestionPatch,
    tasks: BackgroundTasks,
    ctx: EditorCtx,
    engine: Eng,
    settings: Cfg,
) -> IngestionChangeOut:
    """Activate/deactivate a batch (how a bad upload is undone), then rebuild."""
    with session_scope(engine) as s:
        ing = IngestionRepo(s).set_active(ctx, dataset_id, ingestion_id, body.is_active)
        AuditRepo(s).record(
            ctx,
            action="dataset.batch_active_changed",
            target_type="ingestion",
            target_id=ingestion_id,
            details={"is_active": body.is_active},
        )
        out = IngestionOut.model_validate(ing)
    queued = _queue(ctx, engine, settings, tasks, dataset_id, "manual")
    return IngestionChangeOut(ingestion=out, **queued.model_dump())


@router.post("/{dataset_id}/pipeline-runs", status_code=status.HTTP_202_ACCEPTED)
def trigger_run(
    dataset_id: uuid.UUID, tasks: BackgroundTasks, ctx: EditorCtx, engine: Eng, settings: Cfg
) -> RunRequestOut:
    return _queue(ctx, engine, settings, tasks, dataset_id, "manual")
