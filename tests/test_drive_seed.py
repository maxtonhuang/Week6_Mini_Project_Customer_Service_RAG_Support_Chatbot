"""Tests for config.seed_artifacts_from_repo (fixes Colab empty-Drive blank graphs).

Plain-assert style (no pytest import / fixtures) so both `run_tests.py` and `pytest` run it."""
import glob
import os
import tempfile

from ragguard import config


def test_seed_artifacts_from_repo():
    prev = os.environ.get("RAGGUARD_ARTIFACTS")
    with tempfile.TemporaryDirectory() as tmp:
        dst = os.path.join(tmp, "drive_ragguard")
        os.environ["RAGGUARD_ARTIFACTS"] = dst
        try:
            # The committed repo ./artifacts ships results.json + plots.
            assert (config.repo_root() / "artifacts" / "results.json").exists()
            assert not os.path.exists(os.path.join(dst, "results.json"))

            assert config.seed_artifacts_from_repo() is True
            assert os.path.exists(os.path.join(dst, "results.json"))   # results copied
            assert glob.glob(os.path.join(dst, "*.png"))               # at least one plot copied

            # Idempotent: once the active dir has its own results.json, seeding is a no-op.
            assert config.seed_artifacts_from_repo() is False
        finally:
            if prev is None:
                os.environ.pop("RAGGUARD_ARTIFACTS", None)
            else:
                os.environ["RAGGUARD_ARTIFACTS"] = prev


def test_seed_noop_when_active_is_repo():
    prev = os.environ.get("RAGGUARD_ARTIFACTS")
    os.environ.pop("RAGGUARD_ARTIFACTS", None)
    try:
        # With no override and no Drive, artifact_dir() IS repo/artifacts -> nothing to seed.
        if config.artifact_dir().resolve() == (config.repo_root() / "artifacts").resolve():
            assert config.seed_artifacts_from_repo() is False
    finally:
        if prev is not None:
            os.environ["RAGGUARD_ARTIFACTS"] = prev
