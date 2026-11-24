from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from insightflow.core.context import OrgContext
from insightflow.core.errors import ConflictError, NotFoundError
from insightflow.metadata.bootstrap import ensure_demo_org, ensure_org
from insightflow.metadata.db import create_schema, make_engine, session_scope
from insightflow.metadata.repositories import DataSourceRepo, IngestionRepo, RunRepo


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    eng = make_engine(f"sqlite:///{(tmp_path / 'm.sqlite3').as_posix()}")
    create_schema(eng)
    return eng


def _two_orgs(engine: Engine) -> tuple[OrgContext, OrgContext]:
    with session_scope(engine) as s:
        return ensure_demo_org(s, "org-a"), ensure_org(s, "org-b", "Org B")


def test_sqlite_pragmas_enabled(engine: Engine) -> None:
    with engine.connect() as c:
        assert c.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert c.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"


def test_ensure_demo_org_is_idempotent(engine: Engine) -> None:
    with session_scope(engine) as s:
        first = ensure_demo_org(s, "demo")
    with session_scope(engine) as s:
        assert ensure_demo_org(s, "demo") == first


def test_other_org_cannot_read_data_source(engine: Engine) -> None:
    a, b = _two_orgs(engine)
    with session_scope(engine) as s:
        src = DataSourceRepo(s).create(a, name="Retail", domain="ecommerce", kind="file_upload")
        src_id = src.id
    with session_scope(engine) as s:
        assert DataSourceRepo(s).get(a, src_id).name == "Retail"
        with pytest.raises(NotFoundError):
            DataSourceRepo(s).get(b, src_id)
        assert DataSourceRepo(s).list_all(b) == []


def test_duplicate_data_source_name_conflicts(engine: Engine) -> None:
    a, _ = _two_orgs(engine)
    with session_scope(engine) as s:
        DataSourceRepo(s).create(a, name="Retail", domain="ecommerce", kind="file_upload")
    with pytest.raises(ConflictError), session_scope(engine) as s:
        DataSourceRepo(s).create(a, name="Retail", domain="ecommerce", kind="file_upload")


def test_only_one_active_run_per_source(engine: Engine) -> None:
    a, _ = _two_orgs(engine)
    with session_scope(engine) as s:
        src_id = DataSourceRepo(s).create(a, name="R", domain="ecommerce", kind="sample").id
        RunRepo(s).create_queued(a, src_id, trigger="manual")
    with pytest.raises(ConflictError), session_scope(engine) as s:
        RunRepo(s).create_queued(a, src_id, trigger="manual")


def test_finished_run_does_not_block_new_run(engine: Engine) -> None:
    a, _ = _two_orgs(engine)
    with session_scope(engine) as s:
        src_id = DataSourceRepo(s).create(a, name="R", domain="ecommerce", kind="sample").id
        run = RunRepo(s).create_queued(a, src_id, trigger="manual")
        run.status = "succeeded"
    with session_scope(engine) as s:
        assert RunRepo(s).create_queued(a, src_id, trigger="manual").status == "queued"


def test_rejected_upload_does_not_block_same_bytes_later(engine: Engine) -> None:
    a, _ = _two_orgs(engine)
    sha = "a" * 64
    with session_scope(engine) as s:
        src_id = DataSourceRepo(s).create(a, name="R", domain="ecommerce", kind="file_upload").id
        repo = IngestionRepo(s)
        repo.add(a, src_id, original_name="x.csv", sha256=sha, size_bytes=1, status="rejected")
        repo.add(a, src_id, original_name="x.csv", sha256=sha, size_bytes=1, status="stored")
        assert repo.find_stored_by_sha(a, src_id, sha) is not None
    with pytest.raises(ConflictError), session_scope(engine) as s:
        IngestionRepo(s).add(
            a, src_id, original_name="y.csv", sha256=sha, size_bytes=1, status="stored"
        )
