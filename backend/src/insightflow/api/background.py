"""Runs pipelines after the HTTP response is sent (in-process; see ARCHITECTURE.md §3.1)."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.engine import Engine

from insightflow.core.context import OrgContext
from insightflow.core.settings import Settings
from insightflow.pipeline.service import prune_old_runs, run_pipeline

log = logging.getLogger(__name__)


def run_in_background(
    ctx: OrgContext, engine: Engine, settings: Settings, run_id: uuid.UUID
) -> None:
    try:
        runs = run_pipeline(ctx, engine, settings, run_id)
        prune_old_runs(ctx, engine, settings, runs[-1].data_source_id)
    except Exception:  # never let a background failure vanish silently
        log.exception("background pipeline run crashed", extra={"run_id": str(run_id)})
