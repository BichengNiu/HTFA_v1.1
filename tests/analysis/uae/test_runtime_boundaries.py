from pathlib import Path

import pytest

from dashboard.analysis.uae.data_adapter import load_runtime_uae_bundle


def test_valid_industrial_workbook_is_rejected_as_non_uae():
    with pytest.raises(
        ValueError,
        match="不是可识别的阿联酋监测工作簿",
    ):
        load_runtime_uae_bundle(Path("data/工业/经济数据库0202.xlsx"))


def test_runtime_simulation_does_not_create_or_modify_workbooks():
    before = {
        path.resolve(): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in Path("data").rglob("*.xlsx")
    }

    load_runtime_uae_bundle()

    after = {
        path.resolve(): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in Path("data").rglob("*.xlsx")
    }
    assert after == before
