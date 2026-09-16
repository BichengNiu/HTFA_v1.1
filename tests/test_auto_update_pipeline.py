"""Regression tests for the repository's manual online update entrypoint."""

from pathlib import Path

from htfa.jobs.uae_data import update_data


ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "data" / "UAE" / "auto_update_all.bat"


def test_auto_update_batch_does_not_force_cache_only_mode() -> None:
    text = BATCH.read_text(encoding="utf-8")
    assert "--skip-download" not in text


def test_auto_update_batch_covers_every_registered_source() -> None:
    text = BATCH.read_text(encoding="utf-8")
    missing = [name for name in update_data.SOURCES if name not in text]
    assert not missing
