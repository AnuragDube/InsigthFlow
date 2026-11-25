"""Turns registry metrics into SQL over Gold and runs it.

Identifiers (tables, columns, expressions) come only from the trusted registry; request values
(dates, limits) are always bound parameters. Runs on the sandboxed Gold connection.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

import duckdb

from insightflow.analytics.registry import Metric

Value = Decimal | int | float | None
Grain = Literal["day", "month"]
Dimension = Literal["country", "product"]

# Dimension -> (select key, select label, extra join). Fixed SQL fragments, never user text.
_DIMENSIONS: dict[str, tuple[str, str, str]] = {
    "country": ("t.country", "t.country", ""),
    "product": ("t.stock_code", "p.description", " JOIN dim_product p USING (stock_code)"),
}


def _params(start: date, end: date) -> dict[str, object]:
    return {"start": start, "end": end + timedelta(days=1)}  # inclusive end -> exclusive bound


def _from_clause(metric: Metric) -> str:
    src = metric.source
    if src is None:
        raise ValueError(f"{metric.name} is a formula metric")
    if src.query:
        return f"({src.query}) AS t"
    return f"{src.name} AS t"


def _range_filter(metric: Metric) -> str:
    assert metric.source is not None
    col = metric.source.time_column
    return f" WHERE t.{col} >= $start AND t.{col} < $end" if col else ""


def _scalar_sql(metric: Metric) -> str:
    return f"SELECT {metric.expression} FROM {_from_clause(metric)}{_range_filter(metric)}"


def _scalar(con: duckdb.DuckDBPyConnection, sql: str, start: date, end: date) -> Value:
    row = con.execute(sql, _params(start, end)).fetchone()
    value: Value = row[0] if row else None
    return value


def _combine(op: str, a: Value, b: Value) -> Value:
    if op == "difference":
        if a is None:
            return None
        return a - (b or 0)  # type: ignore[operator]
    if a is None or b in (None, 0):
        return None
    return float(a) / float(b)


def compute_kpis(
    con: duckdb.DuckDBPyConnection, metrics: dict[str, Metric], start: date, end: date
) -> dict[str, Value]:
    values: dict[str, Value] = {}
    for name, metric in metrics.items():  # registry order: operands precede formulas
        if metric.kind == "aggregate":
            values[name] = _scalar(con, _scalar_sql(metric), start, end)
        else:
            a, b = (values[o] for o in metric.operands)
            assert metric.op is not None
            values[name] = _combine(metric.op, a, b)
    return values


def compute_metric_with_sql(
    con: duckdb.DuckDBPyConnection,
    metrics: dict[str, Metric],
    name: str,
    start: date,
    end: date,
) -> tuple[Value, list[str]]:
    """Evaluate only the chosen metric and its operands, recording the SQL used."""
    statements: list[str] = []

    def evaluate(metric: Metric) -> Value:
        if metric.kind == "aggregate":
            sql = _scalar_sql(metric)
            statements.append(sql)
            return _scalar(con, sql, start, end)
        left, right = metric.operands
        assert metric.op is not None
        return _combine(metric.op, evaluate(metrics[left]), evaluate(metrics[right]))

    return evaluate(metrics[name]), statements


def compute_series(
    con: duckdb.DuckDBPyConnection, metric: Metric, start: date, end: date, grain: Grain
) -> list[tuple[date, Value]]:
    """Gap-free series (every day/month in range). Additive metrics show 0 for empty periods."""
    if metric.kind != "aggregate" or metric.source is None or not metric.source.time_column:
        raise ValueError(f"{metric.name} has no time series")
    if grain not in ("day", "month"):
        raise ValueError(f"unsupported grain {grain!r}")
    col = metric.source.time_column
    empty = "NULL" if metric.unit == "ratio" else "0"
    sql = f"""
        WITH spine AS (
            SELECT CAST(d AS DATE) AS period
            FROM range(CAST(date_trunc('{grain}', CAST($start AS DATE)) AS TIMESTAMP),
                       CAST($end AS TIMESTAMP), INTERVAL 1 {grain.upper()}) AS r(d)
        ),
        agg AS (
            SELECT CAST(date_trunc('{grain}', t.{col}) AS DATE) AS period,
                   {metric.expression} AS value
            FROM {_from_clause(metric)}{_range_filter(metric)}
            GROUP BY 1
        )
        SELECT s.period, coalesce(a.value, {empty}) FROM spine s LEFT JOIN agg a USING (period)
        ORDER BY s.period
    """
    return [(r[0], r[1]) for r in con.execute(sql, _params(start, end)).fetchall()]


def compute_breakdown(
    con: duckdb.DuckDBPyConnection,
    metric: Metric,
    start: date,
    end: date,
    dimension: Dimension,
    limit: int,
) -> list[tuple[str, str | None, Value]]:
    if dimension not in metric.dimensions or dimension not in _DIMENSIONS:
        raise ValueError(f"{metric.name} cannot be broken down by {dimension!r}")
    key, label, join = _DIMENSIONS[dimension]
    sql = (
        f"SELECT {key} AS key, {label} AS label, {metric.expression} AS value "
        f"FROM {_from_clause(metric)}{join}{_range_filter(metric)} "
        "GROUP BY 1, 2 ORDER BY value DESC NULLS LAST, key LIMIT $limit"
    )
    params = {**_params(start, end), "limit": int(limit)}
    return [(r[0], r[1], r[2]) for r in con.execute(sql, params).fetchall()]
