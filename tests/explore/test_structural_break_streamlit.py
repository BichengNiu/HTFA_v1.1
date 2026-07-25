from streamlit.testing.v1 import AppTest


STRUCTURAL_BREAK_APP = """
import numpy as np
import pandas as pd
import streamlit as st

from dashboard.explore.ui.structural_break import (
    StructuralBreakAnalysisComponent,
)

rng = np.random.default_rng(17)
data = pd.DataFrame(
    {"value": rng.normal(size=72)},
    index=pd.date_range("2020-01-31", periods=72, freq="ME"),
)
StructuralBreakAnalysisComponent().render_analysis_interface(
    st,
    data,
    "structural-break-smoke",
)
"""


def test_structural_break_workflow_is_separate_and_runnable():
    app = AppTest.from_string(STRUCTURAL_BREAK_APP)

    app.run(timeout=30)

    assert not app.exception
    assert app.selectbox("structural_break_variable_select").value == "value"
    assert len(app.multiselect) == 0

    app.selectbox("structural_break_model").set_value("both")
    app.selectbox("structural_break_lag_method").set_value("bic")
    app.button("structural_break_run_test").click()
    app.run(timeout=30)

    assert not app.exception
    assert len(app.dataframe) == 1
    assert app.dataframe[0].value.loc[0, "突变形式"] == (
        "截距与趋势斜率同时突变"
    )


def test_univariate_page_exposes_parallel_tabs():
    app = AppTest.from_string(
        """
from dashboard.explore.ui.univariate_page import (
    render_univariate_analysis_page,
)
render_univariate_analysis_page()
"""
    )

    app.run(timeout=30)

    assert not app.exception
    assert [tab.label for tab in app.tabs] == [
        "平稳性检验",
        "结构突变检验",
    ]
