from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import openpyxl
import pytest

from insightflow.tools.sample_data import ChecksumMismatch, convert_workbook, verify_sha256


def test_convert_workbook_writes_one_csv_per_sheet(tmp_path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Year 2009-2010"
    ws.append(["Invoice", "Quantity", "InvoiceDate", "Price", "Customer ID"])
    ws.append(["489434", 12, datetime(2009, 12, 1, 7, 45), 6.95, 13085])
    ws.append(["489435", 1, datetime(2009, 12, 1, 8, 0), 2.955, None])
    wb.create_sheet("Year 2010-2011").append(["Invoice"])
    src = tmp_path / "in.xlsx"
    wb.save(src)

    out = convert_workbook(src, tmp_path / "out")

    assert [p.name for p in out] == ["Year_2009-2010.csv", "Year_2010-2011.csv"]
    with out[0].open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[1] == ["489434", "12", "2009-12-01 07:45:00", "6.95", "13085"]
    assert rows[2][3:] == ["2.955", ""]


def test_checksum_mismatch_is_refused(tmp_path: Path) -> None:
    f = tmp_path / "x.zip"
    f.write_bytes(b"not the dataset")
    with pytest.raises(ChecksumMismatch):
        verify_sha256(f, "0" * 64)
