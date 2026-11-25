from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect

from insightflow.metadata.db import make_engine
from insightflow.metadata.migrate import pending_model_changes, upgrade_to_head


def test_migrations_create_schema_matching_models(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'm.sqlite3').as_posix()}"
    upgrade_to_head(url)
    tables = set(inspect(make_engine(url)).get_table_names())
    assert {
        "organizations",
        "data_sources",
        "ingestions",
        "pipeline_runs",
        "pipeline_run_inputs",
        "pipeline_stage_runs",
        "quality_results",
        "audit_events",
        "documents",
    } <= tables
    assert pending_model_changes(url) == []
