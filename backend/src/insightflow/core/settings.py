"""Application configuration, read from environment variables prefixed ``INSIGHTFLOW_``.

Secrets never live in code: they come from the environment or a local ``.env`` (gitignored).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INSIGHTFLOW_", env_file=".env", extra="ignore")

    environment: Literal["dev", "test", "demo"] = "dev"
    data_dir: Path = Path("data")
    database_url: str = "sqlite:///data/metadata.sqlite3"
    sample_dir: Path = Path("data/samples/uci")
    demo_org_slug: str = "demo"
    max_upload_mb: int = 200
    cors_origins: list[str] = ["http://localhost:5173"]
    trusted_hosts: list[str] = ["localhost", "127.0.0.1", "testserver"]
    # Interpolated into DuckDB SET statements, so the format is strictly validated.
    duckdb_memory_limit: str = Field(
        default="2GB", pattern=r"^[0-9]{1,6}(\.[0-9]{1,3})?(KB|MB|GB)$"
    )
    duckdb_threads: int = Field(default=4, ge=1, le=64)
    frontend_dist: Path | None = None  # built SPA (frontend/dist) served same-origin when set
    code_version: str = "dev"  # set to the git SHA in deployments (reproducibility)


@lru_cache
def get_settings() -> Settings:
    return Settings()
