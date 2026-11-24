from __future__ import annotations

import csv
from pathlib import Path

from insightflow.domains.loader import load_domain_pack

FIXTURES = Path(__file__).parents[1] / "fixtures" / "ecommerce"


def test_ecommerce_contract_matches_uci_columns() -> None:
    pack = load_domain_pack("ecommerce")
    assert pack.required_columns == [
        "Invoice",
        "StockCode",
        "Description",
        "Quantity",
        "InvoiceDate",
        "Price",
        "Customer ID",
        "Country",
    ]
    assert pack.column_map["Customer ID"] == "customer_id"
    assert pack.column_map["InvoiceDate"] == "invoice_ts"
    assert pack.contract_version == "1"


def test_adjustment_codes_from_profile() -> None:
    pack = load_domain_pack("ecommerce")
    for code in ("POST", "DOT", "M", "C2", "D", "S", "B", "BANK CHARGES", "ADJUST", "AMAZONFEE"):
        assert code in pack.adjustment_codes
    assert pack.adjustment_code_patterns == ["GIFT_%", "TEST%"]


def test_models_dir_holds_sql_models() -> None:
    pack = load_domain_pack("ecommerce")
    assert (pack.models_dir / "silver").is_dir()
    assert (pack.models_dir / "gold").is_dir()


def test_fixture_headers_follow_contract() -> None:
    pack = load_domain_pack("ecommerce")
    for name in ("batch_a.csv", "batch_b.csv"):
        with (FIXTURES / name).open(encoding="utf-8") as f:
            assert next(csv.reader(f)) == pack.required_columns
