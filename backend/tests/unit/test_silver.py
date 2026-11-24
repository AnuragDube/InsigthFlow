from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import pytest
import yaml

from insightflow.core.settings import Settings
from insightflow.domains.loader import load_domain_pack
from insightflow.pipeline.silver import SilverStats, build_silver
from pipeline_helpers import FIX, ingest_fixtures, setup_source

EXPECTED: dict[str, Any] = yaml.safe_load((FIX / "expected.yaml").read_text("utf-8"))


@pytest.fixture
def silver(settings: Settings, tmp_path: Path) -> tuple[SilverStats, Path, Path]:
    engine, ctx, src = setup_source(settings)
    inputs = ingest_fixtures(settings, engine, ctx, src)
    out, quarantine = tmp_path / "silver", tmp_path / "quarantine"
    stats = build_silver(inputs, out, quarantine, load_domain_pack("ecommerce"))
    return stats, out / "order_lines.parquet", quarantine / "rejected.parquet"


def q(path: Path, sql: str) -> list[tuple[Any, ...]]:
    return duckdb.sql(sql.replace("T", f"read_parquet('{path.as_posix()}')", 1)).fetchall()


def test_silver_counts_match_hand_computed(silver: tuple[SilverStats, Path, Path]) -> None:
    stats, _, _ = silver
    e = EXPECTED["silver"]
    assert stats.rows_in == e["rows_in"]
    assert stats.quarantined == e["quarantined"]
    assert stats.overlap_removed == e["overlap_removed"]
    assert stats.rows_out == e["rows_out"]
    assert stats.within_batch_repeats == e["within_batch_repeats"]


def test_reconciliation_holds(silver: tuple[SilverStats, Path, Path]) -> None:
    s, _, _ = silver
    assert s.rows_in == s.rows_out + s.quarantined + s.overlap_removed


def test_multiplicity_rule_keeps_max_copies(silver: tuple[SilverStats, Path, Path]) -> None:
    _, lines, _ = silver
    # A1 appears once in A and once in B -> 1 copy; A3 twice in A, once in B -> 2 copies.
    assert q(lines, "select count(*) from T where invoice_no='1001' and stock_code='85123A'") == [
        (1,)
    ]
    assert q(lines, "select count(*) from T where invoice_no='1002' and stock_code='22633'") == [
        (2,)
    ]


def test_quarantine_has_reason_codes(silver: tuple[SilverStats, Path, Path]) -> None:
    _, _, rejected = silver
    rows = q(rejected, "select invoice_no, reason_code from T order by invoice_no")
    assert rows == [("1009", "bad_timestamp"), ("1010", "bad_quantity")]


def test_types_and_normalization(silver: tuple[SilverStats, Path, Path]) -> None:
    _, lines, _ = silver
    assert q(lines, "select unit_price from T where invoice_no='1011'") == [(Decimal("2.955"),)]
    assert q(lines, "select count(*) from T where customer_id is null") == [
        (EXPECTED["silver"]["null_customer_rows"],)
    ]
    assert q(lines, "select stock_code from T where invoice_no='1015'") == [("GIFT_0001_20",)]


def test_flags(silver: tuple[SilverStats, Path, Path]) -> None:
    _, lines, _ = silver
    flags = q(
        lines,
        "select sum(is_cancellation::int), sum(is_adjustment::int), sum(is_bad_debt::int), "
        "sum(is_writeoff::int) from T",
    )
    assert flags == [(3, 4, 1, 1)]  # C1004,C1014,C1017 | POST,B,GIFT,POST | A1007 | 1006


def test_bad_rows_above_threshold_still_build(settings: Settings, tmp_path: Path) -> None:
    """Silver never fails on bad rows; deciding whether too many is a quality gate (Task 7)."""
    engine, ctx, src = setup_source(settings)
    inputs = ingest_fixtures(settings, engine, ctx, src, names=("batch_a.csv",))
    stats = build_silver(inputs, tmp_path / "s", tmp_path / "q", load_domain_pack("ecommerce"))
    assert stats.quarantined == 2 and stats.overlap_removed == 0
