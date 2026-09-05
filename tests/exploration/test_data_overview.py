from __future__ import annotations

from inspect import signature
from pathlib import Path
from types import SimpleNamespace

from data_overview.core.options import series_style_widget_key

from htfa.exploration.ui.chart_controls import chart_scope
from htfa.exploration.ui.data_overview import (
    CORRELOGRAM_TRANSFORMATION_LABELS,
    CORRELOGRAM_TRANSFORMATION_OPTIONS,
    CORRELOGRAM_VARIABLES_KEY,
    HURST_RESULT_COLUMNS,
    _hurst_interpretation,
    export_data_overview_widget_state,
    render_data_overview,
    restore_data_overview_widget_state,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_univariate_data_overview_keeps_its_own_namespace():
    source = (
        PROJECT_ROOT / "htfa/exploration/ui/data_overview.py"
    ).read_text(encoding="utf-8")
    assert "htfa.models" not in source
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


def test_hurst_result_table_and_interpretation_contract():
    assert HURST_RESULT_COLUMNS == (
        "变量",
        "赫斯特指数",
        "有效观测数",
        "参考解释",
    )
    assert _hurst_interpretation(0.49) == "反持续（H < 0.5）"
    assert _hurst_interpretation(0.5) == "弱依赖/随机性（H ≈ 0.5）"
    assert _hurst_interpretation(0.51) == "持续性（H > 0.5）"


def test_render_data_overview_has_no_compatibility_arguments():
    assert tuple(signature(render_data_overview).parameters) == ("st_obj",)


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
