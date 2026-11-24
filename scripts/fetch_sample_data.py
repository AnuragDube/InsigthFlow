"""Fetch the UCI Online Retail II sample and convert it to CSV.

Usage (from the repo root):  uv run python scripts/fetch_sample_data.py
Writes data/samples/uci/Year_2009-2010.csv and Year_2010-2011.csv (gitignored).
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from insightflow.tools.sample_data import fetch


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=Path("data/samples/uci"))
    parser.add_argument("--cache", type=Path, default=Path("data/samples/_download"))
    args = parser.parse_args()
    for path in fetch(args.dest, cache_dir=args.cache):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        print(f"{path}  {path.stat().st_size:>12,} bytes  sha256={digest}")


if __name__ == "__main__":
    main()
