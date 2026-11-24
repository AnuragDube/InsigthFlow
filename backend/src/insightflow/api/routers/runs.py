from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.engine import Engine

from insightflow.api.deps import get_engine, get_org_context
from insightflow.api.schemas import Page, QualityOut, RunOut, StageOut
from insightflow.core.context import OrgContext
from insightflow.metadata.db import session_scope
from insightflow.metadata.repositories import DataSourceRepo, RunRepo

router = APIRouter(prefix="/api/v1/pipeline-runs", tags=["pipeline runs"])

Ctx = Annotated[OrgContext, Depends(get_org_context)]
Eng = Annotated[Engine, Depends(get_engine)]


@router.get("")
def list_runs(ctx: Ctx, engine: Eng, dataset_id: Annotated[uuid.UUID, Query()]) -> Page[RunOut]:
    with session_scope(engine) as s:
        DataSourceRepo(s).get(ctx, dataset_id)
        return Page(items=[RunOut.model_validate(r) for r in RunRepo(s).list_all(ctx, dataset_id)])


@router.get("/{run_id}")
def get_run(run_id: uuid.UUID, ctx: Ctx, engine: Eng) -> RunOut:
    with session_scope(engine) as s:
        repo = RunRepo(s)
        out = RunOut.model_validate(repo.get(ctx, run_id))
        out.stages = [StageOut.model_validate(st) for st in repo.stages(ctx, run_id)]
        return out


@router.get("/{run_id}/quality")
def get_quality(run_id: uuid.UUID, ctx: Ctx, engine: Eng) -> Page[QualityOut]:
    with session_scope(engine) as s:
        repo = RunRepo(s)
        repo.get(ctx, run_id)
        return Page(items=[QualityOut.model_validate(q) for q in repo.quality(ctx, run_id)])
