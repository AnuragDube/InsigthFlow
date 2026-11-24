from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from insightflow.core.settings import Settings
from insightflow.domains.loader import DomainPack, load_domain_pack
from insightflow.pipeline.gold import build_gold
from insightflow.pipeline.silver import build_silver_in
from insightflow.quality.engine import (
    RuleResult,
    evaluate,
    gate_passed,
    open_gold_for_checks,
    register_stats,
)
from pipeline_helpers import FIX, ingest_fixtures, setup_source


def _silver_results(
    settings: Settings, tmp_path: Path, pack: DomainPack, names: tuple[str | Path, ...]
) -> tuple[list[RuleResult], Path]:
    engine, ctx, src = setup_source(settings)
    inputs = ingest_fixtures(settings, engine, ctx, src, names=names)
    con = duckdb.connect()
    stats = build_silver_in(con, inputs, tmp_path / "s", tmp_path / "q", pack)
    register_stats(con, stats)
    return evaluate(con, pack.quality_rules, "silver"), tmp_path / "s" / "order_lines.parquet"


def by_id(results: list[RuleResult]) -> dict[str, RuleResult]:
    return {r.rule_id: r for r in results}


def test_pack_declares_silver_and_gold_rules() -> None:
    ids = {r.id for r in load_domain_pack("ecommerce").quality_rules}
    assert {
        "quarantine_ratio",
        "row_reconciliation",
        "cross_batch_overlap_removed",
        "within_batch_repeat_ratio",
        "customer_null_ratio",
        "gold_null_keys",
        "gold_orphan_facts",
        "gold_revenue_reconciliation",
        "gold_fact_sales_not_empty",
    } <= ids


def test_fixture_quarantine_ratio_blocks_with_default_threshold(
    settings: Settings, tmp_path: Path
) -> None:
    pack = load_domain_pack("ecommerce")
    results, _ = _silver_results(settings, tmp_path, pack, ("batch_a.csv", "batch_b.csv"))
    r = by_id(results)
    assert r["quarantine_ratio"].passed is False  # 2 of 22 rows > 1%
    assert r["quarantine_ratio"].observed == pytest.approx(2 / 22)
    assert r["row_reconciliation"].passed and r["row_reconciliation"].observed == 0
    assert r["cross_batch_overlap_removed"].observed == 2
    assert r["customer_null_ratio"].passed and r["customer_null_ratio"].severity == "warning"
    assert gate_passed(results) is False


def test_relaxed_threshold_passes_silver_gate(settings: Settings, tmp_path: Path) -> None:
    pack = load_domain_pack("ecommerce").with_threshold("quarantine_ratio", 0.2)
    results, _ = _silver_results(settings, tmp_path, pack, ("batch_a.csv", "batch_b.csv"))
    assert gate_passed(results) is True


def test_many_bad_dates_fail_quarantine_rule(settings: Settings, tmp_path: Path) -> None:
    pack = load_domain_pack("ecommerce").with_threshold("quarantine_ratio", 0.2)
    bad = tmp_path / "bad_dates.csv"
    lines = (FIX / "batch_b.csv").read_text("utf-8").splitlines()
    bad.write_text(
        "\n".join([lines[0]] + [ln.replace("2010-12-0", "20xx-12-0") for ln in lines[1:]]) + "\n",
        "utf-8",
    )
    results, _ = _silver_results(settings, tmp_path, pack, (bad,))
    assert by_id(results)["quarantine_ratio"].passed is False


def test_gold_rules_pass_on_fixtures(settings: Settings, tmp_path: Path) -> None:
    pack = load_domain_pack("ecommerce")
    _, silver_pq = _silver_results(settings, tmp_path, pack, ("batch_a.csv", "batch_b.csv"))
    build_gold(silver_pq, tmp_path / "g", pack)
    con = open_gold_for_checks(tmp_path / "g" / "gold.duckdb", silver_pq)
    results = evaluate(con, pack.quality_rules, "gold")
    assert {r.rule_id for r in results} >= {"gold_null_keys", "gold_revenue_reconciliation"}
    assert all(r.passed for r in results), [r for r in results if not r.passed]
    assert by_id(results)["gold_revenue_reconciliation"].observed == pytest.approx(0)


def test_rule_with_null_observation_fails() -> None:
    from insightflow.quality.rules import QualityRule

    con = duckdb.connect()
    rule = QualityRule("x", "silver", "blocking", "SELECT NULL", "<=", 1, "null means no data")
    assert evaluate(con, [rule], "silver")[0].passed is False
