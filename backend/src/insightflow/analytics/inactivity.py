"""Evaluate a recency rule against later purchases in the same published run."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import duckdb

from insightflow.analytics.segments import LOOKBACK_DAYS, RECENT_DAYS
from insightflow.core.errors import ValidationFailed

HOLDOUT_DAYS = 30


@dataclass(frozen=True)
class InactivityBacktest:
    cohort_from: date
    snapshot_date: date
    holdout_through: date
    customers: int
    flagged: int
    inactive: int
    true_positives: int
    precision: float | None
    recall: float | None
    baseline_rate: float | None


def evaluate_recency(
    con: duckdb.DuckDBPyConnection, first_sale: date, last_sale: date
) -> InactivityBacktest:
    if (last_sale - first_sale).days + 1 < LOOKBACK_DAYS + HOLDOUT_DAYS:
        raise ValidationFailed("This backtest requires at least 120 calendar days of history.")
    snapshot = last_sale - timedelta(days=HOLDOUT_DAYS)
    start = snapshot - timedelta(days=LOOKBACK_DAYS - 1)
    row = con.execute(
        """
        WITH cohort AS (
            SELECT customer_key,
                   date_diff('day', max(invoice_date), $snapshot) >= $recent AS flagged
            FROM fact_sales
            WHERE invoice_date BETWEEN $start AND $snapshot AND customer_key <> 'UNKNOWN'
            GROUP BY customer_key
        ), returned AS (
            SELECT DISTINCT customer_key
            FROM fact_sales
            WHERE invoice_date > $snapshot AND invoice_date <= $end AND customer_key <> 'UNKNOWN'
        )
        SELECT count(*), count(*) FILTER (WHERE flagged),
               count(*) FILTER (WHERE returned.customer_key IS NULL),
               count(*) FILTER (WHERE flagged AND returned.customer_key IS NULL)
        FROM cohort LEFT JOIN returned USING (customer_key)
        """,
        {"snapshot": snapshot, "recent": RECENT_DAYS, "start": start, "end": last_sale},
    ).fetchone()
    assert row is not None
    customers, flagged, inactive, true_positives = row
    return InactivityBacktest(
        start,
        snapshot,
        last_sale,
        customers,
        flagged,
        inactive,
        true_positives,
        true_positives / flagged if flagged else None,
        true_positives / inactive if inactive else None,
        inactive / customers if customers else None,
    )
