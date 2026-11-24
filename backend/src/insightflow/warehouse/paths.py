"""Where analytical files live. Paths are built only from UUIDs, never user-supplied names."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path


def sql_literal(path: Path) -> str:
    """Quote a trusted, app-generated path as a DuckDB string literal (forward slashes)."""
    return "'" + path.as_posix().replace("'", "''") + "'"


@dataclass(frozen=True)
class OrgPaths:
    data_dir: Path
    org_id: uuid.UUID

    @property
    def root(self) -> Path:
        return self.data_dir / "orgs" / str(self.org_id)

    @property
    def tmp(self) -> Path:
        return self.root / "tmp"

    def bronze_root(self, source_id: uuid.UUID) -> Path:
        return self.root / "bronze" / str(source_id)

    def bronze_dir(self, source_id: uuid.UUID, ingest_id: uuid.UUID) -> Path:
        return self.bronze_root(source_id) / f"ingest_id={ingest_id}"

    def silver_dir(self, source_id: uuid.UUID, run_id: uuid.UUID) -> Path:
        return self.root / "silver" / str(source_id) / f"run_id={run_id}"

    def quarantine_dir(self, source_id: uuid.UUID, run_id: uuid.UUID) -> Path:
        return self.root / "quarantine" / str(source_id) / f"run_id={run_id}"

    def gold_dir(self, source_id: uuid.UUID, run_id: uuid.UUID) -> Path:
        return self.root / "gold" / str(source_id) / f"run_id={run_id}"

    def gold_db(self, source_id: uuid.UUID, run_id: uuid.UUID) -> Path:
        return self.gold_dir(source_id, run_id) / "gold.duckdb"
