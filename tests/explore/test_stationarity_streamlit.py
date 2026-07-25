from streamlit.testing.v1 import AppTest


APP_SOURCE = """
import numpy as np
import pandas as pd
import streamlit as st

from dashboard.explore.ui.stationarity import StationarityAnalysisComponent

rng = np.random.default_rng(7)
values = np.zeros(72)
for index in range(1, len(values)):
    values[index] = 100 + 0.4 * (values[index - 1] - 100) + rng.normal()
data = pd.DataFrame(
    {"value": values},
    index=pd.date_range("2020-01-31", periods=72, freq="ME"),
)
StationarityAnalysisComponent().render_analysis_interface(
    st,
    data,
    "streamlit-smoke",
)
"""


def test_stationarity_workflow_renders_and_runs_all_tests():
    app = AppTest.from_string(APP_SOURCE)

    app.run(timeout=30)

    assert not app.exception
    assert app.selectbox("stationarity_variable_select").value == "value"
    assert any("时间序列统计摘要" in block.value for block in app.code)

    app.selectbox("stationarity_transformation_select").select(
        "first_difference"
    )
    app.run(timeout=30)

    assert not app.exception
    assert app.radio("stationarity_test_source").options == [
        "原始变量",
        "处理后变量（一阶差分）",
    ]
    assert len(app.checkbox) == 0

    app.radio("stationarity_test_source").set_value("processed")
    app.multiselect("stationarity_test_methods").set_value(
        ["adf", "kpss", "pp"]
    )
    app.run(timeout=30)
    app.selectbox("stationarity_adf_trend").set_value("n")
    app.selectbox("stationarity_kpss_trend").set_value("ct")
    app.selectbox("stationarity_pp_trend").set_value("ct")
    app.button("stationarity_run_tests").click()
    app.run(timeout=30)

    assert not app.exception
    assert len(app.dataframe) == 1
    assert app.dataframe[0].value["确定性项"].tolist() == [
        "无常数项",
        "趋势平稳（常数项 + 线性趋势）",
        "常数项 + 线性趋势",
    ]
    download = app.get("download_button")[0]
    run_button = app.button("stationarity_run_tests")
    assert download.proto.type == run_button.proto.type == "primary"
    assert len(app.warning) == 0
