from pathlib import Path


def test_explore_does_not_depend_on_generic_ui_component_layer():
    assert not Path("dashboard/core/ui/components/base.py").exists()

    explore_base = Path("dashboard/explore/ui/base.py").read_text(
        encoding="utf-8"
    )
    assert "UIComponent" not in explore_base

    error_source = Path(
        "dashboard/core/ui/utils/error_handler.py"
    ).read_text(encoding="utf-8")
    assert "class UIErrorHandler" not in error_source
    assert "get_ui_error_handler" not in error_source


def test_stateless_explore_wrappers_are_functions():
    pages_source = Path("dashboard/explore/ui/pages.py").read_text(
        encoding="utf-8"
    )
    assert not Path(
        "dashboard/explore/ui/unified_correlation.py"
    ).exists()
    assert "class DataExplorationWelcomePage" not in pages_source
    assert "def render_data_exploration_welcome_page" in pages_source


def test_unused_lead_lag_adapter_is_removed_but_stale_result_guard_remains():
    analysis_source = Path(
        "dashboard/explore/analysis/lead_lag.py"
    ).read_text(encoding="utf-8")
    page_source = Path(
        "dashboard/explore/ui/bivariate_page.py"
    ).read_text(encoding="utf-8")
    assert "def get_overlapping_series" not in analysis_source
    assert "exploration.bivariate.data_signature" in page_source
    assert "_clear_bivariate_results" in page_source


def test_explore_root_has_no_compatibility_export_facade():
    package_source = Path("dashboard/explore/__init__.py").read_text(encoding="utf-8")
    base_source = Path("dashboard/explore/ui/base.py").read_text(encoding="utf-8")

    assert "_LAZY_EXPORTS" not in package_source
    assert "__getattr__" not in package_source
    assert "ABC" not in base_source
    assert "abstractmethod" not in base_source
