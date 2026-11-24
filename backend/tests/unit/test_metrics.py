from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import duckdb
import pytest

from insightflow.analytics.compiler import compute_breakdown, compute_kpis, compute_series
from insightflow.analytics.registry import Metric, load_metrics
from insightflow.core.settings import Settings
from insightflow.warehouse.engine import open_gold
from pipeline_helpers import published_fixture_gold

DEC1, DEC6 = date(2010, 12, 1), date(2010, 12, 6)


@pytest.fixture
def con(settings: Settings) -> Iterator[duckdb.DuckDBPyConnection]:
    engine, ctx, src = published_fixture_gold(settings)
    c = open_gold(ctx, engine, settings, src)
    yield c
    c.close()


@pytest.fixture
def metrics() -> dict[str, Metric]:
    return load_metrics("ecommerce")


def test_registry_defines_p0_metrics(metrics: dict[str, Metric]) -> None:
    assert set(metrics) == {
        "gross_revenue", "returns_value", "net_revenue", "orders", "average_order_value",
        "units_sold", "active_customers", "new_customers", "repeat_customer_rate",
        "return_rate_value",
    }  # fmt: skip
    assert metrics["gross_revenue"].unit == "GBP"
    assert metrics["return_rate_value"].unit == "ratio"
    assert all(m.description for m in metrics.values())


def test_kpis_match_hand_computed(con, metrics) -> None:  # type: ignore[no-untyped-def]
    k = compute_kpis(con, metrics, DEC1, DEC6)
    assert k["gross_revenue"] == Decimal("140.445")
    assert k["returns_value"] == Decimal("6.950")
    assert k["net_revenue"] == Decimal("133.495")
    assert k["orders"] == 7
    assert k["average_order_value"] == pytest.approx(140.445 / 7)
    assert k["units_sold"] == 60
    assert k["active_customers"] == 4
    assert k["new_customers"] == 4
    assert k["repeat_customer_rate"] == pytest.approx(0.25)
    assert k["return_rate_value"] == pytest.approx(6.95 / 140.445)


def test_inclusive_single_day_range(con, metrics) -> None:  # type: ignore[no-untyped-def]
    k = compute_kpis(con, metrics, DEC1, DEC1)
    assert k["gross_revenue"] == Decimal("72.640") and k["orders"] == 2


def test_empty_range_gives_null_not_zero_for_values_and_ratios(con, metrics) -> None:  # type: ignore[no-untyped-def]
    k = compute_kpis(con, metrics, date(2001, 1, 1), date(2001, 1, 31))
    assert k["gross_revenue"] is None and k["orders"] == 0
    assert k["average_order_value"] is None and k["return_rate_value"] is None
    assert k["repeat_customer_rate"] is None


def test_breakdown_by_country(con, metrics) -> None:  # type: ignore[no-untyped-def]
    rows = compute_breakdown(con, metrics["gross_revenue"], DEC1, DEC6, "country", 10)
    assert [(r[0], r[2]) for r in rows] == [
        ("United Kingdom", Decimal("89.640")),
        ("Netherlands", Decimal("39.000")),
        ("Germany", Decimal("8.850")),
        ("France", Decimal("2.955")),
    ]


def test_breakdown_by_product_has_labels(con, metrics) -> None:  # type: ignore[no-untyped-def]
    top = compute_breakdown(con, metrics["gross_revenue"], DEC1, DEC6, "product", 1)
    assert top == [("22633", "HAND WARMER", Decimal("37.000"))]


def test_monthly_series(con, metrics) -> None:  # type: ignore[no-untyped-def]
    assert compute_series(con, metrics["gross_revenue"], DEC1, DEC6, "month") == [
        (date(2010, 12, 1), Decimal("140.445"))
    ]


def test_daily_series_is_gap_free(con, metrics) -> None:  # type: ignore[no-untyped-def]
    series = compute_series(con, metrics["orders"], DEC1, DEC6, "day")
    assert [d for d, _ in series] == [date(2010, 12, d) for d in range(1, 7)]
    assert dict(series)[date(2010, 12, 3)] == 0  # no sales that day, shown as 0 orders


def test_unsupported_dimension_rejected(metrics) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        compute_breakdown(None, metrics["net_revenue"], DEC1, DEC6, "country", 5)  # type: ignore[arg-type]
