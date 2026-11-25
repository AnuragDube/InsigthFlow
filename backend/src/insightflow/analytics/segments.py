"""Explainable customer segments for the e-commerce domain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import duckdb

LOOKBACK_DAYS = 90
RECENT_DAYS = 30
HIGH_VALUE_ORDERS = 3
HIGH_VALUE_SPEND = 100

_RULES = {
    "high_value_repeat": "Bought in the past 30 days, with at least 3 orders and £100 gross spend.",
    "recent_repeat": (
        "Bought in the past 30 days and placed at least 2 orders, below the high-value threshold."
    ),
    "recent_single": "Bought in the past 30 days and placed exactly 1 order.",
    "inactive": "Last purchase was 30 or more days before the snapshot date.",
}


@dataclass(frozen=True)
class CustomerSegment:
    key: str
    definition: str
    customers: int
    orders: int
    gross_revenue: float


def compute_segments(
    con: duckdb.DuckDBPyConnection, start: date, end: date
) -> list[CustomerSegment]:
    rows = con.execute(
        """
        WITH rfm AS (
            SELECT
                date_diff('day', max(invoice_date), $end) AS recency_days,
                count(DISTINCT invoice_no) AS orders,
                sum(revenue) AS gross_revenue
            FROM fact_sales
            WHERE invoice_date BETWEEN $start AND $end AND customer_key <> 'UNKNOWN'
            GROUP BY customer_key
        ), classified AS (
            SELECT *,
                CASE
                    WHEN recency_days >= $recent_days THEN 'inactive'
                    WHEN orders >= $high_orders AND gross_revenue >= $high_spend
                        THEN 'high_value_repeat'
                    WHEN orders >= 2 THEN 'recent_repeat'
                    ELSE 'recent_single'
                END AS segment
            FROM rfm
        )
        SELECT segment, count(*), sum(orders), sum(gross_revenue)
        FROM classified
        GROUP BY segment
        """,
        {
            "start": start,
            "end": end,
            "recent_days": RECENT_DAYS,
            "high_orders": HIGH_VALUE_ORDERS,
            "high_spend": HIGH_VALUE_SPEND,
        },
    ).fetchall()
    summary = {key: (customers, orders, gross) for key, customers, orders, gross in rows}
    result = []
    for key, definition in _RULES.items():
        customers, orders, gross = summary.get(key, (0, 0, 0))
        result.append(CustomerSegment(key, definition, customers, orders, float(gross)))
    return result
