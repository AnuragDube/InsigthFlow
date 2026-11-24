"""Evaluates declarative quality rules and decides whether a run may be published."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import duckdb

from insightflow.pipeline.silver import SilverStats
from insightflow.quality.rules import QualityRule
from insightflow.warehouse.paths import sql_literal


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    stage: str
    severity: str
    passed: bool
    observed: float | None
    threshold: float
    description: str


def _compare(observed: float | None, op: str, threshold: float) -> bool:
    if observed is None or math.isnan(observed):
        return False  # "no data" is never a pass
    if op == "<=":
        return observed <= threshold
    if op == ">=":
        return observed >= threshold
    return observed == threshold


def evaluate(
    con: duckdb.DuckDBPyConnection, rules: list[QualityRule], stage: str
) -> list[RuleResult]:
    results = []
    for rule in (r for r in rules if r.stage == stage):
        row = con.execute(rule.sql).fetchone()
        observed = None if row is None or row[0] is None else float(row[0])
        results.append(
            RuleResult(
                rule_id=rule.id,
                stage=rule.stage,
                severity=rule.severity,
                passed=_compare(observed, rule.op, rule.threshold),
                observed=observed,
                threshold=rule.threshold,
                description=rule.description,
            )
        )
    return results


def gate_passed(results: list[RuleResult]) -> bool:
    return all(r.passed for r in results if r.severity == "blocking")


def register_stats(con: duckdb.DuckDBPyConnection, stats: SilverStats) -> None:
    con.execute(
        "CREATE OR REPLACE TEMP TABLE stats AS SELECT ? AS rows_in, ? AS rows_out, "
        "? AS quarantined, ? AS overlap_removed, ? AS within_batch_repeats",
        [
            stats.rows_in,
            stats.rows_out,
            stats.quarantined,
            stats.overlap_removed,
            stats.within_batch_repeats,
        ],
    )


def open_gold_for_checks(gold_db: Path, silver_parquet: Path) -> duckdb.DuckDBPyConnection:
    """In-memory connection with the run's Gold attached read-only and Silver as a temp view."""
    con = duckdb.connect()
    con.execute(f"ATTACH {sql_literal(gold_db)} AS gold (READ_ONLY)")
    con.execute("USE gold")
    con.execute(
        f"CREATE TEMP VIEW order_lines AS SELECT * FROM read_parquet({sql_literal(silver_parquet)})"
    )
    return con
