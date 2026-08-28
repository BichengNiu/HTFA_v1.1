from pathlib import Path

from dashboard.navigation_config import MODULE_CONFIG


def test_navigation_registers_only_business_modules() -> None:
    assert tuple(MODULE_CONFIG) == (
        "数据预览",
        "监测分析",
        "模型分析",
        "数据探索",
    )


def test_retired_feature_package_and_core_wrappers_are_absent() -> None:
    feature_root = Path("dashboard") / "auth"
    assert not list(feature_root.rglob("*.py"))
    assert not list(feature_root.rglob("*.pyc"))
    assert not Path("dashboard/core/ui/constants.py").exists()

    sidebar = Path(
        "dashboard/core/ui/components/sidebar/renderer.py"
    ).read_text(encoding="utf-8")

    assert "def filter_modules_by_permission(" not in sidebar


def test_explore_core_depends_on_workbook_contract_not_preview_ui_adapter():
    source = Path("dashboard/explore/core/data_source.py").read_text(
        encoding="utf-8"
    )

    assert "dashboard.preview.modules.uae.loader" not in source
    assert "dashboard.preview.core.workbook_parser" in source
