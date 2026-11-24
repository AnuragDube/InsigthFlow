"""The single way to read Gold: a read-only, sandboxed DuckDB connection.

The same configuration is used for every reader (dashboard and NL-to-SQL alike). That is also a
DuckDB requirement: a second connection to a file in the same process must use the same config.
With external access disabled and the configuration locked, SQL on this connection cannot read
or write files, attach databases, install extensions, or loosen its own settings
(verified in tests/security/test_gold_sandbox.py and docs/spikes/).
"""

from __future__ import annotations

import uuid
from typing import Any

import duckdb
from sqlalchemy.engine import Engine

from insightflow.core.context import OrgContext
from insightflow.core.errors import NoPublishedData
from insightflow.core.settings import Settings
from insightflow.metadata.db import session_scope
from insightflow.metadata.repositories import DataSourceRepo
from insightflow.warehouse.paths import OrgPaths


def sandbox_config(settings: Settings) -> dict[str, Any]:
    return {
        "enable_external_access": False,
        "autoinstall_known_extensions": False,
        "autoload_known_extensions": False,
        "memory_limit": settings.duckdb_memory_limit,
        "threads": settings.duckdb_threads,
        "lock_configuration": True,
    }


def open_gold(
    ctx: OrgContext, engine: Engine, settings: Settings, source_id: uuid.UUID
) -> duckdb.DuckDBPyConnection:
    with session_scope(engine) as s:
        run_id = DataSourceRepo(s).get(ctx, source_id).published_run_id
    if run_id is None:
        raise NoPublishedData("This dataset has no published data yet. Run the pipeline first.")
    path = OrgPaths(settings.data_dir, ctx.org_id).gold_db(source_id, run_id)
    return duckdb.connect(str(path), read_only=True, config=sandbox_config(settings))
