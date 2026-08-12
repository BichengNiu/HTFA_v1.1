import pandas as pd

from dashboard.analysis.industrial.utils.chart_creator_unified import (
    create_time_series_chart,
)


def test_active_industrial_chart_path_builds_requested_series():
    index = pd.date_range("2025-01-01", periods=3, freq="MS")
    frame = pd.DataFrame({"增加值": [1.0, 2.0, 3.0]}, index=index)

    figure = create_time_series_chart(frame, ["增加值"])

    assert len(figure.data) == 1
    assert figure.data[0].name == "增加值"
    assert list(figure.data[0].y) == [1.0, 2.0, 3.0]


def test_parallel_industrial_ui_package_was_removed():
    from pathlib import Path

    assert not Path("dashboard/analysis/industrial/ui/__init__.py").exists()


def test_industrial_utils_have_no_package_cycle_or_dead_weighted_pipeline():
    from pathlib import Path

    weighted_source = Path(
        "dashboard/analysis/industrial/utils/weighted_calculation.py"
    ).read_text(encoding="utf-8")
    state_source = Path(
        "dashboard/analysis/industrial/utils/state_manager.py"
    ).read_text(encoding="utf-8")

    assert "from dashboard.analysis.industrial.utils import" not in weighted_source
    assert "calculate_weighted_groups_optimized" not in weighted_source
    assert "class IndustrialStateManager" not in state_source
