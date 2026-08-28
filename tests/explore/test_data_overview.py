from __future__ import annotations

from inspect import signature
from pathlib import Path

from dashboard.explore.ui.data_overview import (
    CORRELOGRAM_TRANSFORMATION_LABELS,
    CORRELOGRAM_TRANSFORMATION_OPTIONS,
    render_data_overview,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_univariate_data_overview_does_not_depend_on_sarimax_ui():
    source = (
        PROJECT_ROOT / "dashboard/explore/ui/data_overview.py"
    ).read_text(encoding="utf-8")
    assert "dashboard.models.SARIMAX" not in source


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
