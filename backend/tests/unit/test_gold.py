from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import pytest
import yaml

from insightflow.core.settings import Settings
from insightflow.domains.loader import load_domain_pack
from insightflow.pipeline.gold import GOLD_TABLES, build_gold
from insightflow.pipeline.silver import build_silver
from pipeline_helpers import FIX, ingest_fixtures, setup_source

E: dict[str, Any] = yaml.safe_load((FIX / "expected.yaml").read_text("utf-8"))["gold"]


@pytest.fixture
def silver_parquet(settings: Settings, tmp_path: Path) -> Path:
    engine, ctx, src = setup_source(settings)
    inputs = ingest_fixtures(settings, engine, ctx, src)
    build_silver(inputs, tmp_path / "s", tmp_path / "q", load_domain_pack("ecommerce"))
    return tmp_path / "s" / "order_lines.parquet"


@pytest.fixture
def gold(silver_parquet: Path, tmp_path: Path) -> duckdb.DuckDBPyConnection:
    build_gold(silver_parquet, tmp_path / "g", load_domain_pack("ecommerce"))
    return duckdb.connect(str(tmp_path / "g" / "gold.duckdb"), read_only=True)


def one(con: duckdb.DuckDBPyConnection, sql: str) -> Any:
    row = con.execute(sql).fetchone()
    assert row is not None
    return row[0]


def test_fact_sales_matches_hand_computed(gold: duckdb.DuckDBPyConnection) -> None:
    assert one(gold, "select count(*) from fact_sales") == E["fact_sales_rows"]
    assert one(gold, "select sum(revenue) from fact_sales") == Decimal(E["gross_revenue"])
    assert one(gold, "select sum(quantity) from fact_sales") == E["units_sold"]
    assert one(gold, "select count(distinct invoice_no) from fact_sales") == E["orders"]


def test_fact_returns_matches_hand_computed(gold: duckdb.DuckDBPyConnection) -> None:
    assert one(gold, "select count(*) from fact_returns") == E["fact_returns_rows"]
    assert one(gold, "select sum(return_value) from fact_returns") == Decimal(E["returns_value"])


def test_dimensions(gold: duckdb.DuckDBPyConnection) -> None:
    assert one(gold, "select count(*) from dim_customer") == E["dim_customer_rows"]
    assert (
        one(gold, "select count(*) from dim_customer where not is_unknown") == E["known_customers"]
    )
    assert one(gold, "select count(*) from dim_product") == E["dim_product_rows"]
    assert (
        one(gold, "select primary_country from dim_customer where customer_key = '12583'")
        == E["primary_country_12583"]
    )
    assert one(gold, "select min(date)::varchar || ' ' || max(date)::varchar from dim_date") == (
        "2010-12-01 2010-12-06"
    )


def test_every_fact_joins_its_dimensions(gold: duckdb.DuckDBPyConnection) -> None:
    for fact in ("fact_sales", "fact_returns"):
        orphans = one(
            gold,
            f"select count(*) from {fact} f "
            "left join dim_customer c using (customer_key) "
            "left join dim_product p using (stock_code) "
            "left join dim_date d on d.date = f.invoice_date "
            "where c.customer_key is null or p.stock_code is null or d.date is null",
        )
        assert orphans == 0, fact


def test_unknown_customer_member(gold: duckdb.DuckDBPyConnection) -> None:
    assert one(gold, "select count(*) from fact_sales where customer_key = 'UNKNOWN'") == 1


def test_gold_is_materialized_tables_not_views(gold: duckdb.DuckDBPyConnection) -> None:
    tables = {r[0] for r in gold.execute("select table_name from duckdb_tables()").fetchall()}
    assert set(GOLD_TABLES) == tables  # nothing else (no Silver/working tables) leaks in
    assert gold.execute("select count(*) from duckdb_views() where not internal").fetchone() == (0,)


def test_gold_exports_parquet(silver_parquet: Path, tmp_path: Path) -> None:
    stats = build_gold(silver_parquet, tmp_path / "g2", load_domain_pack("ecommerce"))
    for table in GOLD_TABLES:
        assert (tmp_path / "g2" / f"{table}.parquet").exists()
    assert stats.table_rows["fact_sales"] == E["fact_sales_rows"]


def test_gold_build_is_deterministic(silver_parquet: Path, tmp_path: Path) -> None:
    pack = load_domain_pack("ecommerce")
    build_gold(silver_parquet, tmp_path / "x", pack)
    build_gold(silver_parquet, tmp_path / "y", pack)
    x = duckdb.connect(str(tmp_path / "x" / "gold.duckdb"), read_only=True)
    y = duckdb.connect(str(tmp_path / "y" / "gold.duckdb"), read_only=True)
    for table in GOLD_TABLES:
        sql = f"select * from {table} order by all"
        assert x.execute(sql).fetchall() == y.execute(sql).fetchall(), table
