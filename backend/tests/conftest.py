from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from insightflow.core.settings import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Isolated settings: every test gets its own data dir and SQLite file."""
    return Settings(
        data_dir=tmp_path / "data",
        database_url=f"sqlite:///{(tmp_path / 'meta.sqlite3').as_posix()}",
        sample_dir=tmp_path / "samples",
        environment="test",
    )


@pytest.fixture
def client_headers() -> dict[str, str]:
    return {"X-InsightFlow-Client": "web"}


@pytest.fixture(autouse=True)
def _no_env_leak(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in ("INSIGHTFLOW_DATA_DIR", "INSIGHTFLOW_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    yield
