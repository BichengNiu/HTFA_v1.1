from pathlib import Path

import pytest

from dashboard.analysis.uae.data_adapter import (
    DEFAULT_UAE_WORKBOOK,
    load_real_uae_bundle,
)


def _snapshot_workbooks(root: Path) -> dict[Path, tuple[int, int]]:
    return {
        path.resolve(): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in root.rglob("*.xlsx")
        if not path.name.startswith("~$")
    }


def test_workbook_snapshot_ignores_excel_owner_files(tmp_path):
    workbook = tmp_path / "report.xlsx"
    owner_file = tmp_path / "~$report.xlsx"
    workbook.write_bytes(b"workbook")
    owner_file.write_bytes(b"owner")

    assert set(_snapshot_workbooks(tmp_path)) == {workbook.resolve()}


def test_valid_industrial_workbook_is_rejected_as_non_uae():
    with pytest.raises(ValueError, match="不是可识别的阿联酋监测工作簿"):
        load_real_uae_bundle(Path("data/工业/经济数据库0202.xlsx"))


def test_real_loader_does_not_create_or_modify_workbooks():
    before = _snapshot_workbooks(Path("data"))
    load_real_uae_bundle(DEFAULT_UAE_WORKBOOK)
    assert _snapshot_workbooks(Path("data")) == before


def test_uae_has_one_runtime_package():
    assert not Path("dashboard/analysis/uae_v2").exists()
