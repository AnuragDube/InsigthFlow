"""Dashboard and metric queries for one published dataset."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

import duckdb
from sqlalchemy.engine import Engine

from insightflow.analytics.compiler import (
    Dimension,
    Grain,
    Value,
    compute_breakdown,
    compute_kpis,
    compute_series,
)
from insightflow.analytics.registry import Metric, load_metrics
from insightflow.core.context import OrgContext
from insightflow.core.errors import NotFoundError, ValidationFailed
from insightflow.core.settings import Settings
from insightflow.metadata.db import session_scope
from insightflow.metadata.repositories import DataSourceRepo, RunRepo
from insightflow.warehouse.engine import open_gold

DAILY_TREND_MAX_DAYS = 62


def as_number(v: Value) -> float | int | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    return v


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date
    min: date
    max: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def previous(self) -> tuple[date, date]:
        prev_end = self.start - timedelta(days=1)
        return prev_end - timedelta(days=self.days - 1), prev_end


def metrics_for(engine: Engine, ctx: OrgContext, source_id: uuid.UUID) -> dict[str, Metric]:
    with session_scope(engine) as s:
        domain = DataSourceRepo(s).get(ctx, source_id).domain
    return load_metrics(domain)


def get_metric(metrics: dict[str, Metric], name: str) -> Metric:
    if name not in metrics:
        raise NotFoundError("Unknown metric.")
    return metrics[name]


def _resolve(con: duckdb.DuckDBPyConnection, start: date | None, end: date | None) -> DateRange:
    row = con.execute("SELECT min(date), max(date) FROM dim_date").fetchone()
    lo: date | None = row[0] if row else None
    hi: date | None = row[1] if row else None
    if lo is None or hi is None:
        raise ValidationFailed("The published dataset has no dates.")
    first, last = start or lo, end or hi
    if first > last:
        raise ValidationFailed("'from' must be on or before 'to'.")
    return DateRange(start=first, end=last, min=lo, max=hi)


def _change(value: Value, previous: Value) -> float | None:
    v, p = as_number(value), as_number(previous)
    if v is None or p is None or p == 0:
        return None
    return (v - p) / abs(p)


def dashboard(
    ctx: OrgContext,
    engine: Engine,
    settings: Settings,
    source_id: uuid.UUID,
    start: date | None,
    end: date | None,
) -> dict[str, object]:
    metrics = metrics_for(engine, ctx, source_id)
    with session_scope(engine) as s:
        run_id = DataSourceRepo(s).get(ctx, source_id).published_run_id
        run = RunRepo(s).get(ctx, run_id) if run_id else None
        quality = RunRepo(s).quality(ctx, run_id) if run_id else []
        finished: datetime | None = run.finished_at if run else None
    con = open_gold(ctx, engine, settings, source_id)  # raises NoPublishedData
    try:
        rng = _resolve(con, start, end)
        current = compute_kpis(con, metrics, rng.start, rng.end)
        prev_start, prev_end = rng.previous()
        previous = compute_kpis(con, metrics, prev_start, prev_end)
        grain: Grain = "day" if rng.days <= DAILY_TREND_MAX_DAYS else "month"
        gross = metrics["gross_revenue"]
        trend = compute_series(con, gross, rng.start, rng.end, grain)
        products = compute_breakdown(con, gross, rng.start, rng.end, "product", 10)
        countries = compute_breakdown(con, gross, rng.start, rng.end, "country", 10)
    finally:
        con.close()
    return {
        "range": {"from": rng.start, "to": rng.end, "min": rng.min, "max": rng.max},
        "kpis": [
            {
                "name": m.name,
                "label": m.label,
                "unit": m.unit,
                "description": m.description,
                "value": as_number(current[m.name]),
                "previous": as_number(previous[m.name]),
                "change": _change(current[m.name], previous[m.name]),
            }
            for m in metrics.values()
        ],
        "trend": {
            "metric": gross.name,
            "grain": grain,
            "points": [{"period": p, "value": as_number(v)} for p, v in trend],
        },
        "top_products": [{"key": k, "label": lbl, "value": as_number(v)} for k, lbl, v in products],
        "countries": [{"key": k, "label": lbl, "value": as_number(v)} for k, lbl, v in countries],
        "freshness": {
            "run_id": run_id,
            "finished_at": finished,
            "quality": {
                "passed": sum(q.passed for q in quality),
                "warnings": sum(not q.passed and q.severity == "warning" for q in quality),
                "failed": sum(not q.passed and q.severity == "blocking" for q in quality),
            },
        },
    }


def series(
    ctx: OrgContext,
    engine: Engine,
    settings: Settings,
    source_id: uuid.UUID,
    name: str,
    start: date | None,
    end: date | None,
    grain: Grain,
) -> dict[str, object]:
    metric = get_metric(metrics_for(engine, ctx, source_id), name)
    con = open_gold(ctx, engine, settings, source_id)
    try:
        rng = _resolve(con, start, end)
        try:
            points = compute_series(con, metric, rng.start, rng.end, grain)
        except ValueError as exc:
            raise ValidationFailed(str(exc)) from exc
    finally:
        con.close()
    return {
        "metric": name,
        "grain": grain,
        "points": [{"period": p, "value": as_number(v)} for p, v in points],
    }


def breakdown(
    ctx: OrgContext,
    engine: Engine,
    settings: Settings,
    source_id: uuid.UUID,
    name: str,
    dimension: Dimension,
    start: date | None,
    end: date | None,
    limit: int,
) -> dict[str, object]:
    metric = get_metric(metrics_for(engine, ctx, source_id), name)
    if dimension not in metric.dimensions:
        raise ValidationFailed(f"'{name}' cannot be broken down by {dimension}.")
    con = open_gold(ctx, engine, settings, source_id)
    try:
        rng = _resolve(con, start, end)
        rows = compute_breakdown(con, metric, rng.start, rng.end, dimension, limit)
    finally:
        con.close()
    return {
        "metric": name,
        "dimension": dimension,
        "items": [{"key": k, "label": lbl, "value": as_number(v)} for k, lbl, v in rows],
    }
