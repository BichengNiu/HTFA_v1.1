from streamlit.testing.v1 import AppTest

from dashboard.explore.ui.chart_controls import (
    _state_key,
    chart_scope,
)


APP_SOURCE = '''
import streamlit as st

from dashboard.explore.ui.chart_controls import (
    chart_scope,
    get_applied_config,
    render_time_series_config_expander,
)

scope = chart_scope("chart-controls-test")
defaults = {
    "title": "Default title",
    "x_title": "Time",
    "y_title": "Value",
    "line_width": 3.0,
    "marker_size": 0.0,
    "max_ticks": 12,
    "y_tick_count": 8,
    "x_start": None,
    "y_start": None,
    "grid_mode": "both",
    "grid_line_style": "solid",
}
applied = get_applied_config(st, scope, defaults)
st.write(applied["title"])
render_time_series_config_expander(st, scope=scope, defaults=defaults)
'''


def test_chart_setting_change_applies_value_without_refresh_button():
    scope = chart_scope("chart-controls-test")
    app = AppTest.from_string(APP_SOURCE)

    app.run(timeout=30)

    title_key = _state_key(scope, "title")
    app.text_input(title_key).set_value("Updated title")
    app.run(timeout=30)
    assert app.markdown[0].value == "Updated title"
    assert len(app.button) == 0
