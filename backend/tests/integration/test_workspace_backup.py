from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

from insightflow.api.app import create_app
from insightflow.core.context import VerifiedIdentity
from insightflow.core.settings import Settings
from insightflow.metadata.browser_sessions import issue_session
from insightflow.metadata.db import session_scope
from insightflow.metadata.memberships import set_role
from pipeline_helpers import FIX

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "backup_workspace.py"
HEADERS = {"X-InsightFlow-Client": "web"}


def test_workspace_cli_backup_restores_published_data_and_rejects_tampering(
    settings: Settings, tmp_path: Path
) -> None:
    # Keep the source metadata inside the data directory, as in the local default.
    source = settings.model_copy(
        update={"database_url": f"sqlite:///{(settings.data_dir / 'source.sqlite3').as_posix()}"}
    )
    with TestClient(create_app(source)) as client:
        dataset = (
            client.post("/api/v1/datasets", json={"name": "Backup source"}, headers=HEADERS)
            .raise_for_status()
            .json()
        )
        url = f"/api/v1/datasets/{dataset['id']}"
        client.post(
            f"{url}/uploads",
            files={"file": ("batch.csv", (FIX / "batch_b.csv").read_bytes())},
            headers=HEADERS,
        ).raise_for_status()

        with session_scope(client.app.state.engine) as session:
            identity = VerifiedIdentity("test", "operator", client.app.state.demo_ctx.org_id)
            set_role(session, identity, "owner")
            session.flush()
            issue_session(session, identity, None)
        expected = client.get(f"{url}/dashboard").raise_for_status().json()
        client.post(
            "/api/v1/documents",
            files={"file": ("policy.txt", b"Refunds take seven days.")},
            headers=HEADERS,
        ).raise_for_status()

    env = {
        **os.environ,
        "INSIGHTFLOW_DATA_DIR": str(source.data_dir),
        "INSIGHTFLOW_DATABASE_URL": source.database_url,
    }

    def manage(*args: str | Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *(str(arg) for arg in args)],
            env=env, capture_output=True, text=True, timeout=30, check=False,
        )  # fmt: skip

    snapshot = tmp_path / "snapshot"
    result = manage("backup", snapshot)
    assert result.returncode == 0, result.stderr
    assert not (snapshot / "data" / "source.sqlite3").exists()
    with closing(sqlite3.connect(snapshot / "metadata.sqlite3")) as database:
        assert database.execute("SELECT count(*) FROM browser_sessions").fetchone() == (0,)
    with closing(sqlite3.connect(source.data_dir / "source.sqlite3")) as database:
        assert database.execute("SELECT count(*) FROM browser_sessions").fetchone() == (1,)
    restored = tmp_path / "restored"
    result = manage("restore", snapshot, restored)
    assert result.returncode == 0, result.stderr
    restored_settings = source.model_copy(
        update={
            "data_dir": restored / "data",
            "database_url": f"sqlite:///{(restored / 'metadata.sqlite3').as_posix()}",
        }
    )
    with TestClient(create_app(restored_settings)) as client:
        assert client.get(f"{url}/dashboard").raise_for_status().json() == expected
        documents = client.get("/api/v1/documents").raise_for_status().json()
        assert [doc["title"] for doc in documents] == ["policy.txt"]

    assert manage("restore", snapshot, restored).returncode == 1
    assert (restored / "metadata.sqlite3").is_file()
    artifact = next((snapshot / "data").rglob("gold.duckdb"))
    with artifact.open("ab") as file:
        file.write(b"test corruption")
    rejected = tmp_path / "rejected"
    bad = manage("restore", snapshot, rejected)
    assert bad.returncode == 1
    assert "checksum" in bad.stderr
    assert not rejected.exists()
