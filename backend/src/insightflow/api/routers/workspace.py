"""Workspace-scoped operational information."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.engine import Engine

from insightflow.api.deps import get_engine, get_org_context, get_settings_dep
from insightflow.core.context import OrgContext
from insightflow.core.settings import Settings
from insightflow.metadata.db import session_scope
from insightflow.metadata.repositories import IngestionRepo

router = APIRouter(prefix="/api/v1/workspace", tags=["workspace"])


class StorageUsage(BaseModel):
    retained_csv_bytes: int
    limit_bytes: int


@router.get("/storage")
def storage_usage(
    ctx: Annotated[OrgContext, Depends(get_org_context)],
    engine: Annotated[Engine, Depends(get_engine)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> StorageUsage:
    with session_scope(engine) as session:
        used = IngestionRepo(session).stored_bytes(ctx)
    return StorageUsage(retained_csv_bytes=used, limit_bytes=settings.workspace_upload_limit_bytes)
