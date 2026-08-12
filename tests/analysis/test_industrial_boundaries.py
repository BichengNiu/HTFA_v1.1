from pathlib import Path

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


def test_industrial_module_has_no_retired_combined_page_or_upload_state():
    source = Path(
        "dashboard/analysis/industrial/enterprise_analysis.py"
    ).read_text(encoding="utf-8")

    assert "render_enterprise_operations_analysis_with_data" not in source
    assert "analysis.industrial.unified_file_uploader" not in source
