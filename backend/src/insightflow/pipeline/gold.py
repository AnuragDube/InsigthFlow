"""Gold: business-ready star schema, materialized inside a per-run ``gold.duckdb``.

Tables (not views over Parquet) so the sandboxed reader needs no file access at all
(SECURITY.md §5). Each table is also exported to Parquet for interop and Spark parity tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb

from insightflow.domains.loader import DomainPack
from insightflow.pipeline.sql_runner import run_models
from insightflow.warehouse.paths import sql_literal

GOLD_TABLES = (
    "fact_sales",
    "fact_returns",
    "dim_date",
    "dim_customer",
    "dim_product",
    "agg_daily_sales",
)


@dataclass(frozen=True)
class GoldStats:
    table_rows: dict[str, int]


def build_gold(
    silver_parquet: Path,
    gold_dir: Path,
    pack: DomainPack,
    *,
    memory_limit: str = "2GB",
    threads: int = 4,
) -> GoldStats:
    gold_dir.mkdir(parents=True, exist_ok=True)
    db_path = gold_dir / "gold.duckdb"
    if db_path.exists():  # a run directory is never reused; a leftover means a crashed attempt
        db_path.unlink()
    con = duckdb.connect(str(db_path))
    try:
        con.execute(f"SET memory_limit = '{memory_limit}'")
        con.execute(f"SET threads = {int(threads)}")
        # TEMP: Silver is an input here, not part of Gold (it must not be queryable by users).
        con.execute(
            "CREATE TEMP TABLE order_lines AS "
            f"SELECT * FROM read_parquet({sql_literal(silver_parquet)})"
        )
        built = run_models(con, pack.models_dir / "gold")
        if tuple(built) != GOLD_TABLES:
            raise RuntimeError(f"unexpected Gold models: {built}")
        rows: dict[str, int] = {}
        for table in GOLD_TABLES:
            con.execute(
                f"COPY (SELECT * FROM {table} ORDER BY ALL) "
                f"TO {sql_literal(gold_dir / f'{table}.parquet')} (FORMAT parquet)"
            )
            result = con.execute(f"SELECT count(*) FROM {table}").fetchone()
            rows[table] = int(result[0]) if result else 0
        con.execute("CHECKPOINT")
        return GoldStats(table_rows=rows)
    finally:
        con.close()
