from pathlib import Path

from htfa.app.navigation.config import MODULE_CONFIG


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
    assert not Path("htfa/app/ui/constants.py").exists()

    sidebar = Path(
        "htfa/app/ui/components/sidebar/renderer.py"
    ).read_text(encoding="utf-8")

    assert "def filter_modules_by_permission(" not in sidebar


def test_explore_core_depends_on_canonical_tabular_contract():
    source = Path("htfa/exploration/core/data_source.py").read_text(
        encoding="utf-8"
    )

    assert "htfa.data.tabular" in source
    assert "htfa.data.tabular_input" not in source
    assert "parse_economic_workbook" not in source
