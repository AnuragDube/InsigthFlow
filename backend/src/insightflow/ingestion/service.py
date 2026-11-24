"""Ingestion: validate an uploaded CSV against the domain contract and store it in Bronze.

Bronze keeps the exact bytes received (``raw.csv``) plus a Parquet copy with every column as
text and lineage columns, so type problems are handled (and reported) in Silver, never lost here.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

import duckdb
from sqlalchemy.engine import Engine

from insightflow.core.context import OrgContext
from insightflow.core.errors import ConflictError, PayloadTooLarge, ValidationFailed
from insightflow.core.ids import new_id
from insightflow.core.settings import Settings
from insightflow.domains.loader import load_domain_pack
from insightflow.metadata.db import session_scope
from insightflow.metadata.models import Ingestion
from insightflow.metadata.repositories import AuditRepo, DataSourceRepo, IngestionRepo
from insightflow.warehouse.paths import OrgPaths, sql_literal

log = logging.getLogger(__name__)
_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class IngestResult:
    ingestion: Ingestion
    created: bool


def _spool(src: BinaryIO, dest: Path, max_bytes: int) -> tuple[str, int]:
    """Stream the upload to disk, hashing as we go and enforcing the size cap."""
    digest, size = hashlib.sha256(), 0
    with dest.open("wb") as out:
        while chunk := src.read(_CHUNK):
            size += len(chunk)
            if size > max_bytes:
                raise PayloadTooLarge("The file is too large.")
            digest.update(chunk)
            out.write(chunk)
    return digest.hexdigest(), size


def _read_header(path: Path) -> list[str]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as f:
            first = f.readline()
    except UnicodeDecodeError as exc:
        raise ValidationFailed("The file is not a UTF-8 text CSV.") from exc
    if not first.strip() or "\x00" in first:
        raise ValidationFailed("The file is empty or not a CSV.")
    return [c.strip() for c in next(csv.reader(io.StringIO(first)))]


def _write_bronze(raw: Path, out_dir: Path, ingest_id: uuid.UUID) -> int:
    """Parquet copy, all VARCHAR. ``rowid`` follows insertion order = CSV line order."""
    parquet = out_dir / "data.parquet"
    con = duckdb.connect()
    try:
        con.execute(
            "CREATE TABLE t AS SELECT * FROM read_csv(?, all_varchar = true, header = true, "
            "delim = ',', quote = '\"', escape = '\"')",
            [raw.as_posix()],
        )
        con.execute(
            f"COPY (SELECT '{ingest_id}' AS _ingest_id, rowid + 1 AS _row_number, * FROM t "
            f"ORDER BY rowid) TO {sql_literal(parquet)} (FORMAT parquet)"
        )
        count = con.execute("SELECT count(*) FROM t").fetchone()
    except duckdb.Error as exc:
        raise ValidationFailed("The CSV could not be parsed.") from exc
    finally:
        con.close()
    return int(count[0]) if count else 0


def _reject(
    ctx: OrgContext, engine: Engine, source_id: uuid.UUID, name: str, sha: str, size: int, why: str
) -> None:
    with session_scope(engine) as s:
        ing = IngestionRepo(s).add(
            ctx, source_id, original_name=name, sha256=sha, size_bytes=size,
            status="rejected", rejection_reason=why,
        )  # fmt: skip
        AuditRepo(s).record(
            ctx, action="dataset.upload", outcome="error", target_type="ingestion",
            target_id=ing.id, details={"reason": why},
        )  # fmt: skip


def ingest_file(
    ctx: OrgContext,
    engine: Engine,
    settings: Settings,
    source_id: uuid.UUID,
    src: BinaryIO,
    original_name: str,
) -> IngestResult:
    with session_scope(engine) as s:
        source = DataSourceRepo(s).get(ctx, source_id)  # 404 for unknown/foreign ids
        pack = load_domain_pack(source.domain)

    paths = OrgPaths(settings.data_dir, ctx.org_id)
    paths.tmp.mkdir(parents=True, exist_ok=True)
    tmp = paths.tmp / f"upload-{new_id()}.part"
    safe_name = Path(original_name).name[:255] or "upload.csv"  # display only, never a path
    try:
        sha, size = _spool(src, tmp, settings.max_upload_mb * 1024 * 1024)

        with session_scope(engine) as s:
            existing = IngestionRepo(s).find_stored_by_sha(ctx, source_id, sha)
        if existing is not None:
            return IngestResult(existing, created=False)

        try:
            header = _read_header(tmp)
            missing = [c for c in pack.required_columns if c not in header]
            if missing:
                raise ValidationFailed(f"Missing required columns: {', '.join(missing)}.")
        except ValidationFailed as exc:
            _reject(ctx, engine, source_id, safe_name, sha, size, exc.detail)
            raise

        ingest_id = new_id()
        out_dir = paths.bronze_dir(source_id, ingest_id)
        out_dir.mkdir(parents=True)
        try:
            os.replace(tmp, out_dir / "raw.csv")
            rows = _write_bronze(out_dir / "raw.csv", out_dir, ingest_id)
            manifest = {
                "ingestion_id": str(ingest_id),
                "original_name": safe_name,
                "sha256": sha,
                "size_bytes": size,
                "row_count": rows,
                "contract_version": pack.contract_version,
            }
            (out_dir / "_manifest.json").write_text(json.dumps(manifest, indent=2), "utf-8")
            with session_scope(engine) as s:
                # Same transaction as the batch: durable "pending work" marker. If the process dies
                # before a run is requested, the startup sweep still processes this batch.
                DataSourceRepo(s).lock(ctx, source_id).rerun_requested_at = datetime.now(UTC)
                ing = IngestionRepo(s).add(
                    ctx, source_id, ingestion_id=ingest_id, original_name=safe_name,
                    sha256=sha, size_bytes=size, status="stored", row_count=rows,
                    storage_path=out_dir.relative_to(paths.root).as_posix(),
                )  # fmt: skip
                AuditRepo(s).record(
                    ctx, action="dataset.upload", target_type="ingestion", target_id=ingest_id,
                    details={"rows": rows, "size_bytes": size},
                )  # fmt: skip
            return IngestResult(ing, created=True)
        except ValidationFailed as exc:
            shutil.rmtree(out_dir, ignore_errors=True)
            _reject(ctx, engine, source_id, safe_name, sha, size, exc.detail)
            raise
        except ConflictError:
            # A concurrent upload of the same bytes won the race: return its ingestion.
            shutil.rmtree(out_dir, ignore_errors=True)
            with session_scope(engine) as s:
                winner = IngestionRepo(s).find_stored_by_sha(ctx, source_id, sha)
            if winner is None:
                raise
            return IngestResult(winner, created=False)
        except BaseException:
            shutil.rmtree(out_dir, ignore_errors=True)
            raise
    finally:
        tmp.unlink(missing_ok=True)
