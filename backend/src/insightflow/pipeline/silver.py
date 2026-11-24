"""Silver: typed, cleaned, flagged order lines from all active Bronze batches."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

import duckdb

from insightflow.domains.loader import DomainPack
from insightflow.pipeline.sql_runner import run_models
from insightflow.warehouse.paths import sql_literal


@dataclass(frozen=True)
class BatchInput:
    ingest_id: uuid.UUID
    parquet: Path
    order: int  # upload order; earlier batches win ties (lineage)


@dataclass(frozen=True)
class SilverStats:
    rows_in: int
    rows_out: int
    quarantined: int
    overlap_removed: int
    within_batch_repeats: int


def _count(con: duckdb.DuckDBPyConnection, sql: str) -> int:
    row = con.execute(sql).fetchone()
    return int(row[0]) if row else 0


def register_inputs(
    con: duckdb.DuckDBPyConnection, inputs: list[BatchInput], pack: DomainPack
) -> None:
    if not inputs:
        raise ValueError("no active batches to process")
    union = " UNION ALL BY NAME ".join(
        f"SELECT *, {int(b.order)} AS _batch_order FROM read_parquet({sql_literal(b.parquet)})"
        for b in inputs
    )
    con.execute(f"CREATE OR REPLACE VIEW bronze AS {union}")
    con.execute("CREATE OR REPLACE TABLE adjustment_codes (code VARCHAR)")
    con.executemany("INSERT INTO adjustment_codes VALUES (?)", [[c] for c in pack.adjustment_codes])
    con.execute("CREATE OR REPLACE TABLE adjustment_patterns (pattern VARCHAR)")
    con.executemany(
        "INSERT INTO adjustment_patterns VALUES (?)", [[p] for p in pack.adjustment_code_patterns]
    )


def build_silver_in(
    con: duckdb.DuckDBPyConnection,
    inputs: list[BatchInput],
    out_dir: Path,
    quarantine_dir: Path,
    pack: DomainPack,
) -> SilverStats:
    """Build Silver inside an existing connection (tables stay available for quality checks)."""
    register_inputs(con, inputs, pack)
    run_models(con, pack.models_dir / "silver")
    out_dir.mkdir(parents=True, exist_ok=True)
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    con.execute(
        "COPY (SELECT * FROM order_lines ORDER BY invoice_ts, invoice_no, _ingest_id, _row_number) "
        f"TO {sql_literal(out_dir / 'order_lines.parquet')} (FORMAT parquet)"
    )
    con.execute(
        "COPY (SELECT * FROM rejected ORDER BY _ingest_id, _row_number) "
        f"TO {sql_literal(quarantine_dir / 'rejected.parquet')} (FORMAT parquet)"
    )
    rows_in = _count(con, "SELECT count(*) FROM typed")
    quarantined = _count(con, "SELECT count(*) FROM rejected")
    rows_out = _count(con, "SELECT count(*) FROM order_lines")
    return SilverStats(
        rows_in=rows_in,
        rows_out=rows_out,
        quarantined=quarantined,
        overlap_removed=rows_in - quarantined - rows_out,
        within_batch_repeats=_count(
            con, "SELECT count(*) FROM order_lines WHERE occurrence_no > 1"
        ),
    )


def build_silver(
    inputs: list[BatchInput], out_dir: Path, quarantine_dir: Path, pack: DomainPack
) -> SilverStats:
    con = duckdb.connect()
    try:
        return build_silver_in(con, inputs, out_dir, quarantine_dir, pack)
    finally:
        con.close()
