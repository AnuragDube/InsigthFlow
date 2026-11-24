"""Download and convert the UCI Online Retail II sample (CC BY 4.0) into contract-shaped CSVs.

Dev-time tool (needs the dev dependency ``openpyxl``). The dataset is never committed to git.
Source: https://archive.ics.uci.edu/dataset/502/online+retail+ii
"""

from __future__ import annotations

import csv
import hashlib
import shutil
import urllib.request
import zipfile
from datetime import date, datetime
from pathlib import Path

UCI_URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
# SHA-256 of the archive as downloaded on 2026-11-24. If UCI republishes the file this changes:
# inspect the new file, then update this constant deliberately.
UCI_ZIP_SHA256 = "572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb"
XLSX_NAME = "online_retail_II.xlsx"


class ChecksumMismatch(Exception):
    pass


def verify_sha256(path: Path, expected: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ChecksumMismatch(
            f"{path.name}: sha256 {digest.hexdigest()} does not match expected {expected}"
        )


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def convert_workbook(xlsx: Path, dest: Path) -> list[Path]:
    """Write each sheet to ``<sheet name with _ for spaces>.csv`` (UTF-8). Returns the paths."""
    import openpyxl  # dev-only dependency, imported lazily

    dest.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    written = []
    try:
        for ws in wb.worksheets:
            out = dest / f"{ws.title.replace(' ', '_')}.csv"
            tmp = out.with_suffix(".csv.part")
            with tmp.open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                for row in ws.iter_rows(values_only=True):
                    writer.writerow([_cell(v) for v in row])
            tmp.replace(out)
            written.append(out)
    finally:
        wb.close()
    return written


def fetch(dest: Path, *, cache_dir: Path) -> list[Path]:
    existing = sorted(dest.glob("*.csv"))
    if existing:
        return existing
    cache_dir.mkdir(parents=True, exist_ok=True)
    archive = cache_dir / "online_retail_ii.zip"
    if not archive.exists():
        part = archive.with_suffix(".part")
        with urllib.request.urlopen(UCI_URL, timeout=300) as resp, part.open("wb") as f:
            shutil.copyfileobj(resp, f)
        part.replace(archive)
    verify_sha256(archive, UCI_ZIP_SHA256)
    with zipfile.ZipFile(archive) as zf:
        if XLSX_NAME not in zf.namelist():
            raise ChecksumMismatch(f"{XLSX_NAME} not found in archive")
        zf.extract(XLSX_NAME, cache_dir)  # fixed member name: no path traversal
    return convert_workbook(cache_dir / XLSX_NAME, dest)
