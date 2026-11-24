"""Programmatic Alembic helpers so migrations ship inside the package."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from insightflow.metadata.db import make_engine
from insightflow.metadata.models import Base

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def alembic_config(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def upgrade_to_head(url: str) -> None:
    command.upgrade(alembic_config(url), "head")


def pending_model_changes(url: str) -> list[Any]:
    """Differences between the migrated database and the models (should be empty)."""
    with make_engine(url).connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"render_as_batch": True})
        return list(compare_metadata(ctx, Base.metadata))
