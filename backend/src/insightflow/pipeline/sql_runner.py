"""Executes a folder of SQL models in order, materializing each as a table.

``10_typed.sql`` becomes table ``typed``. Models are plain SELECTs over tables the caller has
already registered — there is no string templating, so model files cannot be a vector for
injected SQL.
"""

from __future__ import annotations

import re
from pathlib import Path

import duckdb

_MODEL = re.compile(r"^(\d+_)?([a-z][a-z0-9_]*)\.sql$")


def model_files(folder: Path) -> list[tuple[str, Path]]:
    models = []
    for path in sorted(folder.glob("*.sql")):
        m = _MODEL.match(path.name)
        if not m:
            raise ValueError(f"invalid model file name: {path.name}")
        models.append((m.group(2), path))
    return models


def run_models(con: duckdb.DuckDBPyConnection, folder: Path) -> list[str]:
    names = []
    for name, path in model_files(folder):
        sql = path.read_text(encoding="utf-8")
        con.execute(f"CREATE OR REPLACE TABLE {name} AS {sql}")
        names.append(name)
    return names
