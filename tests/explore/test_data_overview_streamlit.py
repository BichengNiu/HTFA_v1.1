from streamlit.testing.v1 import AppTest


APP_SOURCE = '''
from io import BytesIO

import streamlit as st

from dashboard.explore.ui.data_overview import render_data_overview

uploaded = BytesIO(b"date,value\\n2024-01-31,1\\n2024-02-29,2\\n2024-03-31,4\\n2024-04-30,8\\n")
uploaded.name = "overview.csv"
render_data_overview(st, uploaded)
'''


def test_data_overview_renders_original_series_and_summary():
    app = AppTest.from_string(APP_SOURCE)

    app.run(timeout=30)

    assert not app.exception
    assert app.selectbox("data_overview_variable_select").value == "value"
    assert len(app.code) == 1
    assert "时间序列统计摘要" in app.code[0].value
    assert [metric.label for metric in app.metric] == [
        "总观测数",
        "有效观测数",
        "缺失值",
        "识别频率",
        "更新日期",
    ]
    assert len(app.expander) == 2
    grid_selectors = [
        selector for selector in app.selectbox if selector.label == "网格方向"
    ]
    assert len(grid_selectors) == 2
    assert all(
        selector.options == ["横向网格", "纵向网格", "横纵网格"]
        for selector in grid_selectors
    )
    line_style_selectors = [
        selector for selector in app.selectbox if selector.label == "网格线型"
    ]
    assert len(line_style_selectors) == 2
    assert all(
        selector.options == ["实线", "虚线", "点线", "点划线"]
        for selector in line_style_selectors
    )
