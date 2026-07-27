from streamlit.testing.v1 import AppTest


APP_SOURCE = '''
from io import BytesIO

import streamlit as st

from dashboard.explore.ui.bivariate_page import render_bivariate_analysis_page

rows = ["date,target,candidate"]
for day in range(1, 13):
    rows.append(f"2025-01-{day:02d},{day},{day + 1}")
uploaded = BytesIO(("\\n".join(rows) + "\\n").encode("utf-8"))
uploaded.name = "bivariate.csv"

st.session_state["auth.debug_mode"] = True
st.session_state["dashboard.shared_dataset.file"] = uploaded
render_bivariate_analysis_page()
'''


def test_bivariate_page_uses_one_contract_dataset_for_both_analyses():
    app = AppTest.from_string(APP_SOURCE)

    app.run(timeout=30)

    assert not app.exception
    assert app.selectbox("bivariate_table_select").value == "table"
    assert (
        app.session_state["exploration.time_lag_corr.upload_data"]
        is app.session_state["exploration.lead_lag.upload_data"]
    )
    assert (
        app.session_state["exploration.time_lag_corr.file_name"]
        == "bivariate.csv-table"
    )
    assert app.selectbox("lead_lag_target_var").value == "target"


def test_dtw_result_is_hidden_when_a_calculation_parameter_changes():
    app = AppTest.from_string(APP_SOURCE)
    app.run(timeout=30)

    app.button("dtw_analyze_btn_bivariate.csv-table").click()
    app.run(timeout=30)

    assert not app.exception
    assert app.session_state["tools.analysis.dtw.auto_results"]
    saved_signature = app.session_state["tools.analysis.dtw.dtw_signature"]

    app.selectbox(
        "dtw_bivariate.csv-table_standardization_method"
    ).set_value("none")
    app.run(timeout=30)

    assert not app.exception
    assert app.session_state["tools.analysis.dtw.auto_results"] is None
    assert app.session_state["tools.analysis.dtw.dtw_signature"] is None
    assert saved_signature is not None
