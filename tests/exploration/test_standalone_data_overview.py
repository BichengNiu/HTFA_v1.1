from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd

from data_overview.core.options import series_style_widget_key, trim_to_valid_range
from htfa.exploration.ui.data_overview import _build_univariate_overview_dataset


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _navigate_to_univariate_overview(app) -> None:
    next(button for button in app.sidebar.button if button.label == "数据探索").click()
    app.run()
    next(button for button in app.sidebar.button if button.label == "单变量分析").click()
    app.run()


def test_uploaded_univariate_data_opens_in_a_new_session(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    source = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _navigate_to_univariate_overview(source)
    source.sidebar.file_uploader[0].upload(
        "univariate.csv",
        (
            b"date,value\n2020-01-01,1\n2020-02-01,2\n"
            b"2020-03-01,3\n2020-04-01,4\n"
        ),
        "text/csv",
    )
    source.run()

    assert any(
        list(element.value.columns) == ["date", "value"]
        for element in source.dataframe
    )
    source_view_mode = next(
        element
        for element in source.selectbox
        if element.key == "univariate_overview_table_view_mode"
    )
    source_view_mode.select("显示全部")
    source.run()

    launcher = source.get("link_button")
    assert len(launcher) == 1
    url = launcher[0].proto.url
    assert "univariate.csv" not in url
    assert "date,value" not in url

    standalone = AppTest.from_file(
        PROJECT_ROOT / "app.py", default_timeout=60
    )
    standalone.query_params = parse_qs(urlparse(url).query)
    standalone.query_params["unrelated"] = ["preserve"]
    standalone.run()

    assert not standalone.exception
    assert not standalone.file_uploader
    assert not any(item.label == "返回主系统" for item in standalone.button)
    assert any(
        list(element.value.columns) == ["date", "value"]
        for element in standalone.dataframe
    )
    standalone_view_mode = next(
        element
        for element in standalone.selectbox
        if element.key == "univariate_overview_table_view_mode"
    )
    assert standalone_view_mode.value == "显示全部"
    assert source_view_mode.value == "显示全部"
    assert standalone.query_params == {
        "view": ["univariate-overview"],
        "unrelated": ["preserve"],
    }

    standalone_view_mode.select("显示尾10行")
    standalone.run()
    assert standalone_view_mode.value == "显示尾10行"
    assert source_view_mode.value == "显示全部"

    source.sidebar.file_uploader[0].upload(
        "replacement.csv",
        b"date,value\n2021-01-01,10\n2021-02-01,20\n",
        "text/csv",
    )
    source.run()
    source_frame = next(
        element.value
        for element in source.dataframe
        if list(element.value.columns) == ["date", "value"]
    )
    assert source_frame.iloc[0]["value"] == 10

    standalone.run()
    standalone_frame = next(
        element.value
        for element in standalone.dataframe
        if list(element.value.columns) == ["date", "value"]
    )
    assert standalone_frame.iloc[0]["value"] == 1


def test_repeated_source_rerun_keeps_an_unmodified_handoff_token(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    source = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _navigate_to_univariate_overview(source)
    source.sidebar.file_uploader[0].upload(
        "stable.csv",
        b"date,value\n2020-01-01,1\n2020-02-01,2\n",
        "text/csv",
    )
    source.run()
    first_url = source.get("link_button")[0].proto.url

    source.run()
    second_url = source.get("link_button")[0].proto.url

    assert second_url == first_url


def test_standalone_handoff_keeps_reading_and_chart_settings(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    source = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _navigate_to_univariate_overview(source)
    source.sidebar.file_uploader[0].upload(
        "preamble.csv",
        (
            "说明\n来源：测试\n"
            "date,value\n2020-01-01,1\n2020-02-01,2\n"
        ).encode("utf-8"),
        "text/csv",
    )
    source.run()

    next(
        item
        for item in source.number_input
        if item.key == "univariate_overview_preview_variable_name_row"
    ).set_value(3)
    source.run()
    next(
        item
        for item in source.number_input
        if item.key == "univariate_overview_preview_data_start_row"
    ).set_value(4)
    source.run()
    next(
        item
        for item in source.selectbox
        if item.key == "univariate_overview_preview_time_column"
    ).select("无")
    source.run()

    graph_options = next(
        item for item in source.expander if item.label == "图形高级选项"
    )
    graph_options.expanded = True
    source.run()
    next(
        item
        for item in source.text_input
        if item.key == "univariate_overview_preview_title"
    ).set_value("交接后的标题")
    source.run()
    next(
        item
        for item in source.slider
        if item.key == series_style_widget_key(
            "univariate_overview", "value", "markersize"
        )
    ).set_value(7)
    source.run()

    launcher = source.get("link_button")
    assert len(launcher) == 1
    standalone = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60)
    standalone.query_params = parse_qs(urlparse(launcher[0].proto.url).query)
    standalone.run()

    assert not standalone.exception
    assert next(
        item
        for item in standalone.number_input
        if item.key == "univariate_overview_preview_variable_name_row"
    ).value == 3
    assert next(
        item
        for item in standalone.number_input
        if item.key == "univariate_overview_preview_data_start_row"
    ).value == 4
    assert next(
        item
        for item in standalone.selectbox
        if item.key == "univariate_overview_preview_time_column"
    ).value == "无"
    assert next(
        item
        for item in standalone.text_input
        if item.key == "univariate_overview_preview_title"
    ).value == "交接后的标题"
    assert next(
        item
        for item in standalone.slider
        if item.key == series_style_widget_key(
            "univariate_overview", "value", "markersize"
        )
    ).value == 7


def test_univariate_chart_starts_at_first_valid_observation():
    """单变量图表裁掉首个有效值之前的无意义 0 时间点。"""

    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["1955-01-01", "1960-01-01", "2004-01-01", "2005-01-01"]
            ),
            "DFM": [0, 0, 120, 130],
        }
    )
    dataset = _build_univariate_overview_dataset(frame, "dfm.csv", "fingerprint")

    chart_frame = trim_to_valid_range(dataset.frame, ["DFM"])
    assert chart_frame["date"].tolist() == [
        pd.Timestamp("2004-01-01"),
        pd.Timestamp("2005-01-01"),
    ]


def test_invalid_standalone_handoff_has_no_return_button(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60)
    app.query_params = {
        "view": ["univariate-overview"],
        "handoff": ["invalid-token"],
    }
    app.run()

    assert not app.exception
    assert any("链接已失效" in item.value for item in app.error)
    assert not any(item.label == "返回主系统" for item in app.button)
