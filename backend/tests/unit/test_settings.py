import pytest

from insightflow.core.settings import Settings


def test_settings_read_prefixed_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INSIGHTFLOW_MAX_UPLOAD_MB", "5")
    assert Settings().max_upload_mb == 5


def test_settings_defaults_are_local_only() -> None:
    s = Settings()
    assert s.demo_org_slug == "demo"
    assert s.cors_origins == ["http://localhost:5173"]
