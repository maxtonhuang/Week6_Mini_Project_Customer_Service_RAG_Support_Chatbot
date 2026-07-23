"""Tests for config.seed_artifacts_from_repo (fixes Colab empty-Drive blank graphs)."""
from ragguard import config


def test_seed_artifacts_from_repo(tmp_path, monkeypatch):
    dst = tmp_path / "drive_ragguard"
    monkeypatch.setenv("RAGGUARD_ARTIFACTS", str(dst))
    # The committed repo ./artifacts ships results.json + plots.
    assert (config.repo_root() / "artifacts" / "results.json").exists()
    assert not (dst / "results.json").exists()

    assert config.seed_artifacts_from_repo() is True
    assert (dst / "results.json").exists()      # results copied
    assert any(dst.glob("*.png"))               # at least one plot copied

    # Idempotent: once the active dir has its own results.json, seeding is a no-op.
    assert config.seed_artifacts_from_repo() is False


def test_seed_noop_when_active_is_repo(monkeypatch):
    # With no override and no Drive, artifact_dir() IS repo/artifacts -> nothing to seed.
    monkeypatch.delenv("RAGGUARD_ARTIFACTS", raising=False)
    if config.artifact_dir().resolve() == (config.repo_root() / "artifacts").resolve():
        assert config.seed_artifacts_from_repo() is False
