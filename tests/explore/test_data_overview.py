from __future__ import annotations

from inspect import signature
from pathlib import Path
from types import SimpleNamespace

from dashboard.explore.ui.data_overview import (
    CORRELOGRAM_TRANSFORMATION_LABELS,
    CORRELOGRAM_TRANSFORMATION_OPTIONS,
    CORRELOGRAM_VARIABLES_KEY,
    export_data_overview_widget_state,
    migrate_legacy_data_overview_state,
    restore_data_overview_widget_state,
    render_data_overview,
)
from dashboard.explore.ui.chart_controls import chart_scope
from data_overview.core.options import series_style_widget_key

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_univariate_data_overview_keeps_its_own_namespace():
    source = (
        PROJECT_ROOT / "dashboard/explore/ui/data_overview.py"
    ).read_text(encoding="utf-8")
    assert "dashboard.models." not in source
    assert "model_analysis." not in source


def test_correlogram_radio_options_are_four_single_choices():
    assert CORRELOGRAM_TRANSFORMATION_OPTIONS == (
        "original",
        "log",
        "first_difference",
        "log_first_difference",
    )
    assert tuple(CORRELOGRAM_TRANSFORMATION_LABELS.values()) == (
        "原始变量",
        "对数",
        "差分",
        "对数差分",
    )


def test_render_data_overview_has_no_compatibility_arguments():
    assert tuple(signature(render_data_overview).parameters) == ("st_obj",)


def test_legacy_overview_settings_migrate_without_overwriting_current_values():
    state = {
        "sarimax_preview_title": "旧版标题",
        "sarimax_table_view_mode": "显示尾10行",
        "sarimax_preview_sheet": "二表",
        "sarimax_correlogram_vars": ["value"],
        "sarimax_correlogram_transformation_old_scope": "log",
        "sarimax_preview_series_style_deadbeef_markersize": 6,
        "univariate_overview_preview_title": "当前标题",
    }

    migrate_legacy_data_overview_state(SimpleNamespace(session_state=state))

    assert state["univariate_overview_preview_title"] == "当前标题"
    assert state["univariate_overview_table_view_mode"] == "显示尾10行"
    assert state["univariate_overview_preview_sheet"] == "二表"
    assert state[CORRELOGRAM_VARIABLES_KEY] == ["value"]
    assert (
        state["univariate_overview_correlogram_transformation_old_scope"]
        == "log"
    )
    assert state["univariate_overview_preview_series_style_deadbeef_markersize"] == 6


def test_handoff_exports_and_restores_only_selected_correlogram_config():
    scope = chart_scope("data_overview", "value", "correlogram")
    config_key = f"tools.analysis.chart_config.{scope}.nlags"
    unrelated_key = "tools.analysis.chart_config.other_scope.nlags"
    source = SimpleNamespace(
        session_state={
            CORRELOGRAM_VARIABLES_KEY: ["value"],
            config_key: 5,
            unrelated_key: 99,
        }
    )

    exported = export_data_overview_widget_state(source)
    assert exported[config_key] == 5
    assert unrelated_key not in exported

    target_state = {}
    restore_data_overview_widget_state(
        SimpleNamespace(session_state=target_state), exported
    )
    assert target_state[config_key] == 5
    assert unrelated_key not in target_state


def test_handoff_exports_and_restores_dynamic_series_style_settings():
    style_key = series_style_widget_key(
        "univariate_overview", "value", "markersize"
    )
    source = SimpleNamespace(
        session_state={
            "univariate_overview_preview_vars": ["value"],
            CORRELOGRAM_VARIABLES_KEY: ["value"],
            style_key: 7,
        }
    )

    exported = export_data_overview_widget_state(source)
    assert exported[style_key] == 7

    target_state = {}
    restore_data_overview_widget_state(
        SimpleNamespace(session_state=target_state), exported
    )
    assert target_state[style_key] == 7
