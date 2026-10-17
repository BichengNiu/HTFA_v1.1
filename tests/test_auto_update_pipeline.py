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
    assert "-m htfa.jobs.uae_data.update_data" in text
    assert "sys.path.insert" not in text
    assert update_data.resolve_source_names(update_data.parse_args([]).source) == list(
        update_data.SOURCES
    )


def test_comtrade_has_only_one_workbook_merge_owner() -> None:
    assert update_data.workbook_merge_sources(["comtrade"]) == ["comtrade"]
    assert update_data.workbook_merge_sources(["comtrade", "emirates_post", "portwatch"]) == [
        "comtrade", "emirates_post", "portwatch",
    ]


def test_source_batch_launchers_use_runtime_package_entrypoints():
    for module in ("update_data", "merge_workbook"):
        text = (ROOT / "htfa/jobs/uae_data" / f"{module}.bat").read_text(encoding="utf-8-sig")
        assert f"-m htfa.jobs.uae_data.{module} %*" in text
        assert "sys.path.insert" not in text
