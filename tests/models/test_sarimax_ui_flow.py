"""SARIMAX UI 端到端流程测试（AppTest 驱动完整工作流）。"""

from __future__ import annotations

import math
from datetime import date
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest
from Ts.TsSims import simulate_sarima

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _navigate_to_sarimax(app) -> None:
    """通过侧边栏导航到「模型分析 → 单变量模型 → SARIMAX 模型」。"""
    model_button = next(
        button for button in app.sidebar.button if button.label == "模型分析"
    )
    model_button.click()
    app.run()
    sub_button = next(
        button for button in app.sidebar.button if button.label == "单变量模型"
    )
    sub_button.click()
    app.run()


def _navigate_to_univariate_overview(app) -> None:
    """通过侧边栏进入“数据探索 → 单变量分析”。"""
    explore_button = next(
        button for button in app.sidebar.button if button.label == "数据探索"
    )
    explore_button.click()
    app.run()
    sub_button = next(
        button for button in app.sidebar.button if button.label == "单变量分析"
    )
    sub_button.click()
    app.run()


def _prepare_model_app(app, payload, *, model_prefix: str = "sarimax") -> None:
    """在指定模型 Tab 的独立数据输入区上传文件。"""
    _navigate_to_sarimax(app)
    uploader = next(
        element
        for element in app.file_uploader
        if element.key == f"model_analysis.{model_prefix}.upload.uploader"
    )
    uploader.upload(*payload)
    app.run()
    assert not app.exception
    _by_key(app.button, f"{model_prefix}_start_processing_button").click()
    app.run()
    assert not app.exception


def _open_standalone_univariate_overview(app, payload):
    """通过新标签页令牌在独立会话中打开单变量数据概览。"""
    from streamlit.testing.v1 import AppTest

    _navigate_to_univariate_overview(app)
    app.sidebar.file_uploader[0].upload(*payload)
    app.run()
    launcher = app.get("link_button")
    assert len(launcher) == 1
    standalone = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60)
    standalone.query_params = parse_qs(urlparse(launcher[0].proto.url).query)
    standalone.run()
    assert not standalone.exception
    return standalone


def _sample_csv() -> tuple[str, bytes, str]:
    """生成带日期列的 AR(1) 模拟数据 CSV。"""
    simulated = simulate_sarima(n=60, order=(1, 0, 0), ar=[0.6], seed=42)
    index = pd.date_range("2020-01-01", periods=60, freq="MS")
    frame = pd.DataFrame(
        {"date": index.strftime("%Y-%m-%d"), "value": simulated.data}
    )
    return (
        "sample.csv",
        frame.to_csv(index=False).encode("utf-8"),
        "text/csv",
    )


def _preamble_csv() -> tuple[str, bytes, str]:
    """生成前两行是说明、第三行是变量名的 CSV。"""
    content = (
        "这是数据说明\n"
        "来源：测试\n"
        "date,sales,exog\n"
        "2020-01-01,10,1\n"
        "2020-02-01,11,2\n"
        "2020-03-01,12,3\n"
    )
    return "preamble.csv", content.encode("utf-8"), "text/csv"


def _changing_header_csv() -> tuple[str, bytes, str]:
    """生成切换变量名行后表头和时间列名称都会变化的 CSV。"""
    content = (
        "文件说明\n"
        "old_date,old_value\n"
        "2020-01-01,10\n"
        "2020-02-01,11\n"
        "new_date,new_value\n"
        "2021-01-01,20\n"
        "2021-02-01,21\n"
    )
    return "changing-header.csv", content.encode("utf-8"), "text/csv"


def _multi_sample_csv() -> tuple[str, bytes, str]:
    """生成含两个指标的月度 CSV，用于页面级分面测试。"""
    index = pd.date_range("2020-01-01", periods=12, freq="MS")
    frame = pd.DataFrame(
        {
            "date": index.strftime("%Y-%m-%d"),
            "value_a": range(12),
            "value_b": range(20, 32),
        }
    )
    return "multi-sample.csv", frame.to_csv(index=False).encode("utf-8"), "text/csv"


def _dynamic_sample_csv() -> tuple[str, bytes, str]:
    """生成目标和两个连续解释变量，供 RDL/ARDL 工作流使用。"""
    index = pd.date_range("2020-01-01", periods=60, freq="MS")
    frame = pd.DataFrame(
        {
            "date": index.strftime("%Y-%m-%d"),
            "value": [10.0 + step * 0.08 + math.sin(step / 3) for step in range(60)],
            "policy": [1.0 + step * 0.05 + math.cos(step / 4) for step in range(60)],
            "price": [4.0 + step * 0.03 + math.sin(step / 5) for step in range(60)],
        }
    )
    return "dynamic.csv", frame.to_csv(index=False).encode("utf-8"), "text/csv"


def _dynamic_sample_csv_with_missing_exog() -> tuple[str, bytes, str]:
    """生成含缺失外生变量的 SARIMAX 测试数据。"""
    name, content, mime = _dynamic_sample_csv()
    frame = pd.read_csv(BytesIO(content))
    frame.loc[5, "policy"] = None
    return name, frame.to_csv(index=False).encode("utf-8"), mime


def _preprocessed_range_csv() -> tuple[str, bytes, str]:
    """生成首尾值会被默认预处理规则排除的日期数据。"""
    content = (
        "date,value\n"
        "2020-01-01,0\n"
        "2020-02-01,10\n"
        "2020-03-01,11\n"
        "2020-04-01,12\n"
        "2020-05-01,-1\n"
        "2020-06-01,14\n"
    )
    return "preprocessed-range.csv", content.encode("utf-8"), "text/csv"


def _by_key(elements, key: str):
    return next(element for element in elements if element.key == key)


def _assert_completed_progress(app) -> None:
    """断言自动选阶页面保留已完成的候选评估进度条。"""
    progress = app.get("progress")
    assert len(progress) == 1
    assert progress[0].value == 100
    assert "候选模型评估完成" in progress[0].text


class _FakeTrendSelector:
    def __init__(self, selected):
        self.selected = selected
        self.kwargs = None

    def multiselect(self, _label, **kwargs):
        self.kwargs = kwargs
        return self.selected


@pytest.mark.parametrize(
    ("selected", "expected"),
    [
        ([], "n"),
        (["常数项"], "c"),
        (["线性趋势"], "t"),
        (["常数项", "线性趋势"], "ct"),
    ],
)
def test_trend_multiselect_maps_to_ts_code(selected, expected):
    from dashboard.models.SARIMAX.ui.model_options import (
        _render_trend_selector,
    )

    widget = _FakeTrendSelector(selected)
    assert _render_trend_selector(widget, "test") == expected
    assert widget.kwargs["options"] == ("常数项", "线性趋势")


def test_dynamic_regression_data_input_skips_preview(monkeypatch):
    """动态回归数据区只显示读取设置，处理后进入模型训练。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _navigate_to_sarimax(app)
    uploader = next(
        element
        for element in app.file_uploader
        if element.key == "model_analysis.sarimax.upload.uploader"
    )
    uploader.upload(*_sample_csv())
    app.run()

    assert not app.exception
    _by_key(app.number_input, "sarimax_model_preview_variable_name_row")
    _by_key(app.number_input, "sarimax_model_preview_data_start_row")
    _by_key(app.selectbox, "sarimax_model_preview_time_column")
    assert not any(element.key == "sarimax_target_select" for element in app.selectbox)
    assert _by_key(app.button, "sarimax_start_processing_button").label == "开始处理"

    _by_key(app.button, "sarimax_start_processing_button").click()
    app.run()
    assert not app.exception
    _by_key(app.selectbox, "sarimax_target_select")
    _by_key(app.multiselect, "sarimax_exog_select")

    assert not any(
        element.key == "sarimax_model_preview_vars" for element in app.multiselect
    )
    assert not any(
        element.key.startswith("sarimax_model_table_")
        for element in app.selectbox
    )
    assert not any(
        element.key == "sarimax_model_preview_title" for element in app.text_input
    )
    assert not app.dataframe


def test_training_preprocessing_selector(monkeypatch):
    """数据输入区提供可多选的去零和去负替换参数。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _prepare_model_app(app, _dynamic_sample_csv())

    preprocessing = _by_key(app.multiselect, "sarimax_data_preprocessing")
    assert tuple(preprocessing.options) == ("去零", "去负")
    assert preprocessing.value == ["去零", "去负"]


def test_training_missing_value_selector(monkeypatch):
    """数据输入区在数据替换右侧提供缺失值处理选项，默认不处理。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _prepare_model_app(app, _dynamic_sample_csv())

    replacement = _by_key(app.multiselect, "sarimax_data_preprocessing")
    missing = _by_key(app.selectbox, "sarimax_missing_value_method")
    assert replacement.label == "数据替换"
    assert missing.label == "缺失值处理"
    assert tuple(missing.options) == (
        "无",
        "向前填补",
        "向后填补",
        "线性内插",
        "样条内插",
        "多项式内插",
        "卡尔曼滤波",
    )
    assert missing.value == "无"


def test_train_forecast_slider_uses_preprocessed_dates(monkeypatch):
    """训练滑轨边界取预处理后的共同有效日期。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _prepare_model_app(app, _preprocessed_range_csv())

    sample_window = _by_key(app.slider, "sarimax_train_forecast_window")
    assert pd.to_datetime(sample_window.min, unit="us").date() == date(2020, 2, 1)
    assert pd.to_datetime(sample_window.max, unit="us").date() == date(2020, 6, 1)
    assert tuple(
        pd.to_datetime(value, unit="us").date() for value in sample_window.value
    ) == (date(2020, 2, 1), date(2020, 6, 1))
    assert not app.date_input


def test_training_requires_a_valid_time_column(monkeypatch):
    """不选择时间列时训练区报错，而不是静默隐藏时间范围。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _prepare_model_app(app, _sample_csv())

    time_column = _by_key(
        app.selectbox,
        "sarimax_model_preview_time_column",
    )
    time_column.set_value("无")
    app.run()
    _by_key(app.button, "sarimax_start_processing_button").click()
    app.run()

    assert not app.exception
    assert any("没有找到有效时间列" in element.value for element in app.error)
    assert not app.date_input
    assert not any(
        element.key == "sarimax_fit_button" for element in app.button
    )


def test_full_workflow_via_ui(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _prepare_model_app(app, _sample_csv())
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["SARIMAX", "RDL", "ARDL"]
    assert not any(
        control.key == "sarimax_model_family" for control in app.segmented_control
    )
    assert any(
        element.key == "model_analysis.rdl.upload.uploader"
        for element in app.file_uploader
    )
    assert any(
        element.key == "model_analysis.ardl.upload.uploader"
        for element in app.file_uploader
    )
    title_texts = " ".join(element.value for element in app.markdown)
    assert "数据文件" not in title_texts
    assert "① 模型训练" not in title_texts
    assert "② 残差诊断" not in title_texts
    assert "③ 模型预测" not in title_texts
    assert not app.sidebar.file_uploader
    assert any(
        element.key == "model_analysis.sarimax.upload.uploader"
        for element in app.file_uploader
    )
    sample_window = _by_key(app.slider, "sarimax_train_forecast_window")
    train_start, train_end = (
        pd.to_datetime(value, unit="us").date()
        for value in sample_window.value
    )
    assert date(2020, 1, 1) <= train_start <= train_end < date(2024, 12, 1)

    # ① 模型训练：默认手动配置 (1,0,1)，拟合按钮可用并执行
    fit_button = _by_key(app.button, "sarimax_fit_button")
    assert not fit_button.disabled
    assert not _by_key(app.checkbox, "sarimax_enforce_stationarity").value
    assert not _by_key(app.checkbox, "sarimax_enforce_invertibility").value
    fit_button.click()
    app.run()
    assert not app.exception
    assert any(item.value == "**参数估计结果**" for item in app.markdown)
    assert not any(item.label == "参数摘要" for item in app.expander)
    assert not app.get("progress")
    assert not app.metric
    assert not app.success
    assert not any("模型优化状态" in element.value for element in app.markdown)
    forecast_window = _by_key(app.select_slider, "sarimax_forecast_window")
    forecast_start, forecast_end = forecast_window.value
    assert forecast_start >= train_start
    assert forecast_start == pd.Timestamp(forecast_window.options[0]).date()
    assert forecast_end <= train_end
    assert date(2025, 12, 1).isoformat() in forecast_window.options
    assert not any(
        element.key == "sarimax_forecast_oos_steps" for element in app.number_input
    )
    assert not _by_key(app.checkbox, "sarimax_forecast_ci").value
    assert not any(
        element.key == "sarimax_forecast_alpha" for element in app.radio
    )
    assert not any(
        element.key == "sarimax_forecast_alpha" for element in app.selectbox
    )
    assert _by_key(app.checkbox, "sarimax_forecast_dynamic").label == "动态预测"

    _by_key(app.checkbox, "sarimax_forecast_ci").set_value(True)
    app.run()
    assert not app.exception
    assert _by_key(app.checkbox, "sarimax_forecast_ci").value
    assert _by_key(app.radio, "sarimax_forecast_alpha").value == 0.05

    # ② 残差诊断：模型估计后按建议滞后阶数自动执行。
    assert not app.exception
    assert any("残差自相关" in str(element.value) for element in app.dataframe)
    assert not any(element.key == "sarimax_diag_button" for element in app.button)
    assert not any(element.key == "sarimax_diag_lags" for element in app.number_input)
    assert any(element.key == "sarimax_diag_download" for element in app.download_button)

    # ③ 模型预测：默认范围为训练样本，可显式扩展到样本外。
    forecast_button = _by_key(app.button, "sarimax_forecast_button")
    assert not forecast_button.disabled
    forecast_button.click()
    app.run()
    assert not app.exception
    forecast_table = next(
        element.value
        for element in app.dataframe
        if list(element.value.columns)
        == ["日期", "真实值", "预测值", "预测下界", "预测上界"]
    )
    forecast_end = date.fromisoformat(forecast_table["日期"].iloc[0])
    forecast_start = date.fromisoformat(forecast_table["日期"].iloc[-1])
    assert forecast_end == _by_key(app.select_slider, "sarimax_forecast_window").value[1]
    assert (
        forecast_start
        == _by_key(app.select_slider, "sarimax_forecast_window").value[0]
    )
    assert forecast_end >= forecast_start
    assert any("训练样本区间" in element.value for element in app.caption)
    assert any("当前预测区间" in element.value for element in app.caption)
    assert not any("2082" in element.value for element in app.caption)
    assert not any("预测图无法绘制" in element.value for element in app.warning)
    download = _by_key(app.download_button, "sarimax_forecast_download")
    assert download.label == "下载结果"
    evaluation_tabs = {tab.label for tab in app.tabs}
    assert {"训练期评估", "样本外评估"}.issubset(evaluation_tabs)
    assert _by_key(app.number_input, "sarimax_forecast_training_horizon")
    assert _by_key(app.number_input, "sarimax_forecast_oos_horizon")
    assert _by_key(app.button, "sarimax_forecast_training_button")
    assert _by_key(app.button, "sarimax_forecast_oos_button")
    _by_key(app.button, "sarimax_forecast_oos_button").click()
    app.run()
    assert not app.exception
    assert not any(
        "样本外滚动回测失败" in element.value for element in app.error
    )


def test_forecast_window_can_extend_out_of_sample(monkeypatch):
    """预测滑轨可直接选择训练区间外日期。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _prepare_model_app(app, _sample_csv())

    _by_key(app.slider, "sarimax_train_forecast_window").set_value(
        (date(2020, 1, 1), date(2023, 12, 1))
    )
    app.run()
    _by_key(app.button, "sarimax_fit_button").click()
    app.run()
    assert not app.exception

    forecast_window = _by_key(app.select_slider, "sarimax_forecast_window")
    forecast_start = forecast_window.value[1]
    forecast_window.set_value((forecast_start, date(2025, 2, 1)))
    app.run()
    assert not app.exception

    _by_key(app.button, "sarimax_forecast_button").click()
    app.run()
    assert not app.exception
    forecast_table = next(
        element.value
        for element in app.dataframe
        if list(element.value.columns)
        == ["日期", "真实值", "预测值", "预测下界", "预测上界"]
    )
    assert date.fromisoformat(forecast_table["日期"].iloc[0]) == date(2025, 2, 1)
    assert date.fromisoformat(forecast_table["日期"].iloc[-1]) == forecast_start
    assert not any("预测图无法绘制" in element.value for element in app.warning)


def test_log_differenced_forecast_starts_after_state_initialization(monkeypatch):
    """log 差分模型默认预测不应把弥散初始化值送入结果契约。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _prepare_model_app(app, _dynamic_sample_csv())

    _by_key(app.checkbox, "sarimax_response_log").set_value(True)
    _by_key(app.number_input, "sarimax_d").set_value(1)
    app.run()
    assert not app.exception

    _by_key(app.button, "sarimax_fit_button").click()
    app.run()
    assert not app.exception

    forecast_window = _by_key(app.select_slider, "sarimax_forecast_window")
    raw_train_start = _by_key(app.slider, "sarimax_train_forecast_window").value[0]
    train_start = (
        pd.to_datetime(raw_train_start, unit="us").date()
        if isinstance(raw_train_start, (int, float))
        else pd.Timestamp(raw_train_start).date()
    )
    forecast_start = forecast_window.value[0]
    assert forecast_start > train_start

    _by_key(app.checkbox, "sarimax_forecast_dynamic").set_value(True)
    app.run()
    assert not app.exception
    _by_key(app.button, "sarimax_forecast_button").click()
    app.run()
    assert not app.exception
    assert any(
        list(element.value.columns)
        == ["日期", "真实值", "预测值", "预测下界", "预测上界"]
        for element in app.dataframe
    )


def test_training_slider_limits_fit_and_invalidates_result(monkeypatch):
    """训练滑轨仅传入所选样本，修改后不保留旧拟合结果。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _prepare_model_app(app, _dynamic_sample_csv())
    assert not app.exception

    time_range = _by_key(app.slider, "sarimax_train_forecast_window")
    time_range.set_value((date(2021, 1, 1), date(2023, 12, 1)))
    app.run()
    assert not app.exception

    _by_key(app.button, "sarimax_fit_button").click()
    app.run()
    assert not app.exception
    assert not app.metric

    _by_key(app.multiselect, "sarimax_data_preprocessing").set_value(["去零"])
    app.run()
    assert not app.exception
    assert not any(metric.label == "AIC" for metric in app.metric)

    _by_key(app.button, "sarimax_start_processing_button").click()
    app.run()
    assert not app.exception

    response_log = _by_key(app.checkbox, "sarimax_response_log")
    response_log.set_value(True)
    app.run()
    assert not app.exception
    assert not any(metric.label == "AIC" for metric in app.metric)

    _by_key(app.button, "sarimax_fit_button").click()
    app.run()
    assert not app.exception
    assert not app.metric

    _by_key(app.number_input, "sarimax_p").set_value(2)
    app.run()
    assert not app.exception
    assert any(
        "完成模型训练后可查看残差诊断结果" in item.value
        for item in app.info
    )

    _by_key(app.slider, "sarimax_train_forecast_window").set_value(
        (date(2022, 1, 1), date(2023, 12, 1))
    )
    app.run()
    assert not app.exception
    assert not any(metric.label == "AIC" for metric in app.metric)


def test_forecast_prefills_future_exog_from_dataset(monkeypatch):
    """预测页从训练范围之外的数据行预填外生变量路径。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _prepare_model_app(app, _dynamic_sample_csv())

    _by_key(app.multiselect, "sarimax_exog_select").set_value(["policy"])
    _by_key(app.slider, "sarimax_train_forecast_window").set_value(
        (date(2020, 1, 1), date(2023, 12, 1))
    )
    app.run()
    _by_key(app.button, "sarimax_fit_button").click()
    app.run()

    assert not app.exception
    _by_key(app.select_slider, "sarimax_forecast_window").set_value(
        (date(2023, 12, 1), date(2024, 12, 1))
    )
    app.run()
    source = _by_key(app.selectbox, "sarimax_future_exog_source_0")
    assert source.value == "policy"
    assert not any("还有" in warning.value for warning in app.warning)
    forecast_button = _by_key(app.button, "sarimax_forecast_button")
    assert not forecast_button.disabled
    forecast_button.click()
    app.run()
    assert not app.exception
    assert any(
        list(element.value.columns)
        == ["日期", "真实值", "预测值", "预测下界", "预测上界"]
        for element in app.dataframe
    )


def test_auto_mode_workflow_via_ui(monkeypatch):
    """自动选阶模式：切换配置方式、缩小搜索范围后拟合出候选表。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _prepare_model_app(app, _sample_csv())
    assert not app.exception

    # 切换到自动选阶，并把范围缩到 4 个组合
    _by_key(app.segmented_control, "sarimax_config_mode").set_value("自动选阶")
    app.run()
    assert not app.exception
    assert _by_key(app.number_input, "sarimax_auto_s").max == 365
    _by_key(app.slider, "sarimax_auto_p_range").set_value((0, 1))
    _by_key(app.slider, "sarimax_auto_q_range").set_value((0, 1))
    _by_key(app.slider, "sarimax_auto_d_range").set_value((0, 0))
    _by_key(app.slider, "sarimax_auto_P_range").set_value((0, 0))
    _by_key(app.slider, "sarimax_auto_Q_range").set_value((0, 0))
    _by_key(app.slider, "sarimax_auto_D_range").set_value((0, 0))
    app.run()
    assert not app.exception
    assert _by_key(app.checkbox, "sarimax_response_log").label == "目标变量取对数"
    assert _by_key(
        app.checkbox, "sarimax_auto_enforce_stationarity"
    ).label == "强制 AR 多项式平稳"
    assert not _by_key(app.checkbox, "sarimax_auto_enforce_stationarity").value
    assert _by_key(
        app.checkbox, "sarimax_auto_enforce_invertibility"
    ).label == "强制 MA 多项式可逆"
    assert not _by_key(app.checkbox, "sarimax_auto_enforce_invertibility").value
    assert not any(
        item.value in {"搜索范围", "模型设置"} for item in app.markdown
    )
    assert any("网格搜索将尝试 4 个模型组合" in c.value for c in app.caption)
    assert any("候选模型按规模自动调度" in c.value for c in app.caption)

    fit_button = _by_key(app.button, "sarimax_fit_button")
    assert not fit_button.disabled
    fit_button.click()
    app.run()
    assert not app.exception
    _assert_completed_progress(app)
    assert any("候选评估完成" in item.value for item in app.info)
    assert not any("本次候选调度" in c.value for c in app.caption)
    assert not app.metric
    assert not app.success
    assert not any("最终采用模型：" in m.value for m in app.markdown)
    criterion_table = next(
        element.value
        for element in app.dataframe
        if list(element.value.columns) == ["模型", "AIC", "BIC", "HQIC", "AICC"]
    )
    assert len(criterion_table) == 4
    assert all(")(" in label for label in criterion_table["模型"])
    assert all("(0, 0, 0, 0)" in label for label in criterion_table["模型"])
    criterion_radio = _by_key(
        app.radio,
        "sarimax_auto_selection_criterion",
    )
    assert set(criterion_radio.options) == {"AIC", "BIC", "HQIC", "AICC"}
    other_model = _by_key(app.selectbox, "sarimax_auto_selection_model")
    assert len(other_model.options) == 5
    assert other_model.value is None
    aic_min_label = criterion_table.loc[criterion_table["AIC"].idxmin(), "模型"]
    other_label = next(
        label for label in criterion_table["模型"] if label != aic_min_label
    )
    other_model.set_value(other_label)
    app.run()
    assert not app.exception
    assert _by_key(app.selectbox, "sarimax_auto_selection_model").value == other_label

    _by_key(app.radio, "sarimax_auto_selection_criterion").set_value("BIC")
    app.run()
    assert not app.exception
    assert _by_key(app.selectbox, "sarimax_auto_selection_model").value is None
    assert not app.metric
    assert not app.success


def test_sarimax_sparse_order_operator_and_roots_controls_render(monkeypatch):
    """标准 SARIMAX 页面显示稀疏阶、外生算子与创新/roots 分析。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=90).run()
    _prepare_model_app(app, _dynamic_sample_csv())
    _by_key(app.multiselect, "sarimax_exog_select").set_value(["policy"])
    app.run()

    _by_key(app.text_input, "sarimax_ar_lags").set_value("1,3")
    _by_key(app.text_input, "sarimax_ma_lags")
    _by_key(app.text_input, "sarimax_seasonal_ar_lags")
    _by_key(app.text_input, "sarimax_seasonal_ma_lags")
    _by_key(app.dataframe, "sarimax_exog_operators")
    app.run()
    assert not app.exception

    _by_key(app.button, "sarimax_fit_button").click()
    app.run()
    assert not app.exception
    assert _by_key(app.number_input, "sarimax_innovation_irf_steps").value == 20
    assert any("ARMA 创新脉冲响应" in item.value for item in app.markdown)
    assert any("Roots 稳定性" in item.value for item in app.markdown)
    assert any("Roots 稳定性表" in item.value for item in app.markdown)
    assert any("ARMA 创新脉冲响应图" in item.value for item in app.markdown)
    assert any("Roots 稳定性图" in item.value for item in app.markdown)


def test_sarimax_exog_log_switch_prefixes_parameter_estimate(monkeypatch):
    """每个外生变量独立取对数，并在参数结果中保留 log 前缀。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=90).run()
    _prepare_model_app(app, _dynamic_sample_csv())
    _by_key(app.multiselect, "sarimax_exog_select").set_value(["policy"])
    app.run()

    log_switch = _by_key(app.checkbox, "sarimax_exog_log_policy")
    assert log_switch.label == "policy 取对数"
    assert not log_switch.value
    log_switch.set_value(True)
    app.run()
    assert not app.exception

    _by_key(app.button, "sarimax_fit_button").click()
    app.run()
    assert not app.exception
    result = app.session_state["model_analysis.sarimax.fitted_result"]
    assert "log.policy" in result.params
    assert any("log.policy" in element.value for element in app.code)


def test_sarimax_missing_exog_keeps_fit_button_enabled(monkeypatch):
    """SARIMAX 外生变量缺失时显示提示但不禁用拟合按钮。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=90).run()
    _prepare_model_app(app, _dynamic_sample_csv_with_missing_exog())
    _by_key(app.multiselect, "sarimax_exog_select").set_value(["policy"])
    app.run()

    assert not app.exception
    fit_button = _by_key(app.button, "sarimax_fit_button")
    assert not fit_button.disabled
    assert any(
        "外生变量存在 1 个缺失值" in item.value for item in app.warning
    )


def test_sarimax_ar2_roots_show_cycle_diagnostic(monkeypatch):
    """连续 AR(1, 2) 模型在 Roots 区域显示周期识别结果。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=90).run()
    _prepare_model_app(app, _dynamic_sample_csv())
    _by_key(app.text_input, "sarimax_ar_lags").set_value("1,2")
    app.run()

    _by_key(app.button, "sarimax_fit_button").click()
    app.run()

    assert not app.exception
    assert any("AR(2) 周期识别" in item.value for item in app.markdown)
    assert any("周期由 AR(2) 复根的角频率计算" in item.value for item in app.caption)


def _open_model_tab(app, model_prefix: str, mode: str) -> None:
    """初始化一个独立模型 Tab；只有 SARIMAX 显示配置方式控件。"""
    _prepare_model_app(app, _dynamic_sample_csv(), model_prefix=model_prefix)
    _by_key(app.multiselect, f"{model_prefix}_exog_select").set_value(["policy"])
    app.run()
    if model_prefix == "sarimax":
        _by_key(app.segmented_control, f"{model_prefix}_config_mode").set_value(mode)
        app.run()
    assert not app.exception


def test_rdl_manual_workflow_via_ui(monkeypatch):
    """RDL 只显示手动误差阶数并可完成拟合。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=90).run()
    _navigate_to_sarimax(app)
    _open_model_tab(app, "rdl", "手动配置")
    assert _by_key(app.dataframe, "rdl_input_table")
    assert _by_key(app.number_input, "rdl_error_p").value == 1
    assert not any(item.key == "rdl_config_mode" for item in app.segmented_control)
    _by_key(app.button, "rdl_fit_button").click()
    app.run()
    assert not app.exception
    assert not app.metric
    assert not app.success
    assert not any("自动选阶" in item.value for item in app.markdown)


def test_rdl_intervention_controls_are_scoped_and_add_i_row(monkeypatch):
    """RDL 开启干预后显示冲击控件与独立 I 输入行。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=90).run()
    _open_model_tab(app, "rdl", "手动配置")

    intervention = _by_key(app.checkbox, "rdl_intervention_analysis")
    assert intervention.label == "干预分析"
    assert not intervention.value
    assert not any(
        item.key == "rdl_intervention_kind" for item in app.selectbox
    )

    intervention.set_value(True)
    app.run()
    assert not app.exception
    assert _by_key(app.selectbox, "rdl_intervention_kind").value == "单期冲击（pulse）"
    assert _by_key(app.selectbox, "rdl_intervention_pulse_date")
    assert not any(
        item.key == "rdl_intervention_start" for item in app.get("select_slider")
    )
    table = _by_key(app.dataframe, "rdl_input_table").value
    assert "I（干预变量）" in table["变量"].tolist()


def test_rdl_intervention_pulse_fits_and_renders_effect_analysis(monkeypatch):
    """RDL pulse I 可拟合，并在分析页展示独立的干预结果。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=90).run()
    _open_model_tab(app, "rdl", "手动配置")
    _by_key(app.checkbox, "rdl_intervention_analysis").set_value(True)
    app.run()
    _by_key(app.button, "rdl_fit_button").click()
    app.run()

    assert not app.exception
    result = app.session_state["model_analysis.rdl.fitted_result"]
    assert tuple(result.distributed_lags) == ("policy", "intervention")
    assert any("RDL 干预分析" in item.value for item in app.markdown)
    assert any("样本外预测场景暂未开放" in item.value for item in app.info)
    table = next(
        frame.value
        for frame in app.dataframe
        if {"I 干预路径", "有干预 Y", "无干预 Y", "干预差异"}.issubset(
            frame.value.columns
        )
    )
    assert {"I 干预路径", "有干预 Y", "无干预 Y", "干预差异"}.issubset(
        table.columns
    )
    assert any(
        "I 动态权重" in frame.value.columns for frame in app.dataframe
    )
    assert any(
        "分子主动滞后" in frame.value.columns for frame in app.dataframe
    )


def test_rdl_intervention_switches_from_step_to_inclusive_temporary_window(
    monkeypatch,
):
    """冲击类型切换时，单日期和闭区间 slider 与模型类型同步。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=90).run()
    _open_model_tab(app, "rdl", "手动配置")
    _by_key(app.checkbox, "rdl_intervention_analysis").set_value(True)
    app.run()

    kind = _by_key(app.selectbox, "rdl_intervention_kind")
    kind.set_value("持续冲击（step）")
    app.run()
    assert not app.exception
    step_slider = _by_key(app.get("select_slider"), "rdl_intervention_start")
    assert isinstance(step_slider.value, tuple)
    assert len(step_slider.value) == 2
    assert pd.Timestamp(step_slider.value[1]) == pd.Timestamp(
        step_slider.options[-1]
    )
    step_slider.set_range(
        step_slider.value[0],
        pd.Timestamp(step_slider.options[0]),
    )
    app.run()
    step_slider = _by_key(app.get("select_slider"), "rdl_intervention_start")
    assert pd.Timestamp(step_slider.value[1]) == pd.Timestamp(
        step_slider.options[-1]
    )
    assert not any(
        item.key == "rdl_intervention_window" for item in app.get("select_slider")
    )

    kind = _by_key(app.selectbox, "rdl_intervention_kind")
    assert "区间冲击（interval）" in kind.options
    kind.set_value("区间冲击（interval）")
    app.run()
    assert not app.exception
    assert _by_key(app.get("select_slider"), "rdl_intervention_window")
    assert not any(
        item.key == "rdl_intervention_start" for item in app.get("select_slider")
    )


def test_rdl_intervention_timestamp_display_uses_meaningful_precision():
    """冲击日期标签按实际时间戳精度显示，不给日度追加零时分秒。"""
    from dashboard.models.SARIMAX.ui.model_options_rdl import (
        _build_intervention_timestamp_formatter,
    )

    daily = pd.date_range("2025-01-01", periods=2, freq="D")
    daily_formatter = _build_intervention_timestamp_formatter(daily)
    assert daily_formatter(daily[0]) == "2025-01-01"
    assert "00:00:00" not in daily_formatter(daily[0])

    minute_dates = pd.date_range("2025-01-01 09:30", periods=2, freq="min")
    minute_formatter = _build_intervention_timestamp_formatter(minute_dates)
    assert minute_formatter(minute_dates[0]) == "2025-01-01 09:30"

    second_dates = pd.date_range("2025-01-01 09:30:15", periods=2, freq="s")
    second_formatter = _build_intervention_timestamp_formatter(second_dates)
    assert second_formatter(second_dates[0]) == "2025-01-01 09:30:15"


def test_rdl_intervention_can_fit_without_ordinary_exog(monkeypatch):
    """启用干预分析后允许 I-only RDL。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=90).run()
    _open_model_tab(app, "rdl", "手动配置")
    _by_key(app.checkbox, "rdl_intervention_analysis").set_value(True)
    app.run()
    _by_key(app.multiselect, "rdl_exog_select").set_value([])
    app.run()
    _by_key(app.number_input, "rdl_error_p").set_value(0)
    _by_key(app.number_input, "rdl_error_q").set_value(0)
    app.run()
    _by_key(app.button, "rdl_fit_button").click()
    app.run()

    assert not app.exception
    assert tuple(app.session_state["model_analysis.rdl.fitted_result"].distributed_lags) == (
        "intervention",
    )


def test_rdl_intervention_log_target_exposes_relative_effect(monkeypatch):
    """RDL 干预分析在 log(Y) 下展示原始尺度相对变化。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=90).run()
    _open_model_tab(app, "rdl", "手动配置")
    _by_key(app.checkbox, "rdl_response_log").set_value(True)
    _by_key(app.checkbox, "rdl_intervention_analysis").set_value(True)
    app.run()
    _by_key(app.number_input, "rdl_error_p").set_value(0)
    _by_key(app.number_input, "rdl_error_q").set_value(0)
    app.run()
    _by_key(app.button, "rdl_fit_button").click()
    app.run()

    assert not app.exception
    result = app.session_state["model_analysis.rdl.fitted_result"]
    assert result.log
    table = next(
        frame.value
        for frame in app.dataframe
        if "相对变化（%）" in frame.value.columns
    )
    assert table["相对变化（%）"].notna().any()
    assert any("log(Y)" in item.value for item in app.caption)


def test_rdl_intervention_change_clears_previous_fit(monkeypatch):
    """改变冲击日期后旧拟合结果立即失效。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=90).run()
    _open_model_tab(app, "rdl", "手动配置")
    _by_key(app.checkbox, "rdl_intervention_analysis").set_value(True)
    app.run()
    _by_key(app.button, "rdl_fit_button").click()
    app.run()
    assert app.session_state["model_analysis.rdl.fitted_result"] is not None

    date_selector = _by_key(app.selectbox, "rdl_intervention_pulse_date")
    options = list(date_selector.options)
    date_selector.set_value(options[0])
    app.run()

    assert app.session_state["model_analysis.rdl.fitted_result"] is None


def test_sarimax_does_not_render_rdl_intervention_checkbox(monkeypatch):
    """干预分析控件只属于 RDL 页面。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=90).run()
    _open_model_tab(app, "sarimax", "手动配置")

    assert not any(
        item.key == "sarimax_intervention_analysis" for item in app.checkbox
    )


def test_ardl_does_not_render_rdl_intervention_checkbox(monkeypatch):
    """干预分析控件不属于 ARDL 页面。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=90).run()
    _open_model_tab(app, "ardl", "手动配置")

    assert not any(
        item.key == "ardl_intervention_analysis" for item in app.checkbox
    )


def test_ardl_manual_sarima_error_workflow_via_ui(monkeypatch):
    """ARDL 只显示手动滞后，并可配置 SARIMA 误差后完成拟合。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=90).run()
    _navigate_to_sarimax(app)
    _open_model_tab(app, "ardl", "手动配置")
    assert _by_key(app.dataframe, "ardl_input_table")
    assert _by_key(app.number_input, "ardl_error_p").value == 1
    assert _by_key(app.number_input, "ardl_error_q").value == 1
    assert not any(item.key == "ardl_config_mode" for item in app.segmented_control)
    assert not any(
        item.key == "sarimax_rdl_input_table" for item in app.dataframe
    )
    _by_key(app.number_input, "ardl_error_p").set_value(0)
    _by_key(app.number_input, "ardl_error_q").set_value(0)
    app.run()
    _by_key(app.button, "ardl_fit_button").click()
    app.run()
    assert not app.exception
    assert any(item.value == "**残差诊断图**" for item in app.markdown)
    result = app.session_state["model_analysis.ardl.fitted_result"]
    assert result.error_order == (0, 0, 0)
    assert result.error_seasonal_order == (0, 0, 0, 0)
    assert result.ardl_order == (1, 0)
def test_data_table_options_via_ui(monkeypatch):
    """数据表高级选项：行数、筛选直接作用于预览表、统计量。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    app = _open_standalone_univariate_overview(app, _sample_csv())

    # 独立页不显示原主系统上传器，变量选择与预览控件位于页面主区域。
    assert not app.file_uploader
    _by_key(app.multiselect, "univariate_overview_preview_vars")

    # 两个高级选项 expander 均存在，分别位于表格和时间序列图下方
    assert len(app.expander) >= 2
    assert app.expander[0].label == "数据表高级选项"
    assert app.expander[1].label == "图形高级选项"

    def preview_frame():
        """上方预览表（列名为 date + value）。"""
        frames = [
            element.value
            for element in app.dataframe
            if list(element.value.columns) == ["date", "value"]
        ]
        assert len(frames) == 1
        return frames[0]

    # 默认：预览表显示前 10 行
    assert len(preview_frame()) == 10
    assert preview_frame().iloc[0]["date"] == "2020-01-01"

    # 行数、筛选和时间控件都在数据表高级选项中，表格下方不再渲染行数控件。
    app.expander[0].expanded = True
    app.run()
    assert not app.exception
    view_mode = _by_key(app.selectbox, "univariate_overview_table_view_mode")
    assert view_mode.value == "显示头10行"
    _by_key(app.selectbox, "univariate_overview_table_filter_col")
    filter_op = _by_key(app.selectbox, "univariate_overview_table_filter_op")
    assert "≠" in filter_op.options
    assert _by_key(app.number_input, "univariate_overview_table_filter_val").label == "值"
    # 月度数据 → 时间筛选按频率渲染为「时间范围」预设下拉
    # 训练区有一个样本日期滑轨；预览表的月度时间筛选不额外渲染 date_input。
    _by_key(app.selectbox, "univariate_overview_table_time_preset")
    assert not any(element.key == "univariate_overview_table_view_head" for element in app.checkbox)
    assert not any(element.key == "univariate_overview_table_view_tail" for element in app.checkbox)

    # 数值筛选：value ≥ 2.0 → 上方预览表直接变为筛选结果（少于 10 行）
    _by_key(app.selectbox, "univariate_overview_table_filter_col").select("value")
    _by_key(app.number_input, "univariate_overview_table_filter_val").set_value(2.0)
    app.run()
    assert not app.exception
    filtered = preview_frame()
    assert 0 < len(filtered) < 10
    # 统计量表出现（describe 转置：count/mean/std/...）
    assert any(
        {"count", "mean", "std", "min", "max"} <= set(element.value.columns)
        for element in app.dataframe
    )

    # 清除数值筛选后选择「显示尾10行」→ 预览表显示最后 10 行
    _by_key(app.selectbox, "univariate_overview_table_filter_col").select("无")
    app.run()
    _by_key(app.selectbox, "univariate_overview_table_view_mode").select("显示尾10行")
    app.run()
    assert not app.exception
    assert _by_key(app.selectbox, "univariate_overview_table_view_mode").value == "显示尾10行"
    # 预览表显示全部数据的最后 10 行（60 行数据末尾为 2024-12）
    tailed = preview_frame()
    assert len(tailed) == 10
    assert tailed.iloc[-1]["date"] == "2024-12-01"

    # 时间预设：月度数据选「过去3个月」→ 最后 3 行（2024-10 ~ 2024-12）
    _by_key(app.selectbox, "univariate_overview_table_time_preset").select("过去3个月")
    app.run()
    assert not app.exception
    assert len(preview_frame()) == 3
    stats = next(
        element.value
        for element in app.dataframe
        if {"count", "mean", "std", "min", "max"}
        <= set(element.value.columns)
    )
    assert int(stats.loc["value", "count"]) == 3

    # 自定义年月：限定 2023-01 ~ 2023-12 → 12 行（尾10行视图截断为 10）
    _by_key(app.selectbox, "univariate_overview_table_time_preset").select("自定义")
    app.run()
    assert not app.exception
    assert _by_key(app.selectbox, "univariate_overview_table_time_start")
    assert _by_key(app.selectbox, "univariate_overview_table_time_end")
    _by_key(app.selectbox, "univariate_overview_table_time_start").select("2023-01")
    _by_key(app.selectbox, "univariate_overview_table_time_end").select("2023-12")
    app.run()
    assert not app.exception
    assert len(preview_frame()) == 10  # 12 行结果被尾10行视图截断
    stats = next(
        element.value
        for element in app.dataframe
        if {"count", "mean", "std", "min", "max"}
        <= set(element.value.columns)
    )
    assert int(stats.loc["value", "count"]) == 12

    # 选择「显示全部」+ 时间范围回「全部」→ 显示全部 60 行
    _by_key(app.selectbox, "univariate_overview_table_view_mode").select("显示全部")
    _by_key(app.selectbox, "univariate_overview_table_time_preset").select("全部")
    app.run()
    assert not app.exception
    assert len(preview_frame()) == 60
    # 选择指定行数 17 → 显示前 17 行
    _by_key(app.selectbox, "univariate_overview_table_view_mode").select("显示指定行数")
    app.run()
    assert not app.exception
    _by_key(app.number_input, "univariate_overview_table_view_rows").set_value(17)
    app.run()
    assert not app.exception
    assert len(preview_frame()) == 17
    assert preview_frame().iloc[0]["date"] == "2020-01-01"


def test_page_level_facet_renders_independent_plots(monkeypatch):
    """分面在 Streamlit 页面中生成多个独立图，而不是单个子图 Figure。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    app = _open_standalone_univariate_overview(app, _multi_sample_csv())

    variables = _by_key(app.multiselect, "univariate_overview_preview_vars")
    variables.set_value(["value_a", "value_b"])
    app.run()
    assert not app.exception
    assert len(app.image) == 5  # 时间序列图 + 两个变量各自的 ACF/PACF 图
    assert any(
        list(element.value.columns)
        == ["变量", "赫斯特指数", "有效观测数", "参考解释"]
        for element in app.dataframe
    )

    _by_key(app.checkbox, "univariate_overview_preview_facet").check()
    app.run()
    assert not app.exception
    assert len(app.image) == 6  # 两个分面时间序列图 + 两个变量各自的 ACF/PACF 图
    image_columns = [
        column
        for column in app.columns
        if any(type(child).__name__ == "Image" for child in column.children.values())
    ]
    assert len(image_columns) == 6

    _by_key(app.number_input, "univariate_overview_preview_facet_cols").set_value(2)
    app.run()
    assert not app.exception
    assert len(app.image) == 6

    app.expander[1].expanded = True
    app.run()
    assert not app.exception
    assert _by_key(app.checkbox, "univariate_overview_preview_sharex").value is True
    assert _by_key(app.checkbox, "univariate_overview_preview_sharey").value is False
    assert _by_key(app.checkbox, "univariate_overview_preview_sharex").proto.disabled
    assert _by_key(app.checkbox, "univariate_overview_preview_sharey").proto.disabled
    assert _by_key(app.number_input, "univariate_overview_preview_legend_bbox_x").proto.disabled
    assert _by_key(app.number_input, "univariate_overview_preview_legend_bbox_y").proto.disabled
    assert _by_key(app.number_input, "univariate_overview_preview_legend_cols").proto.disabled
    assert _by_key(app.number_input, "univariate_overview_preview_legend_size")
    _by_key(app.selectbox, "univariate_overview_preview_legend_loc").select("upper right")
    app.run()
    assert not app.exception
    assert app.expander[1].proto.id
    assert _by_key(app.number_input, "univariate_overview_preview_legend_bbox_x").proto.disabled
    assert _by_key(app.number_input, "univariate_overview_preview_legend_bbox_y").proto.disabled
    assert any(
        element.key == "univariate_overview_preview_grid_style" for element in app.selectbox
    )
    assert any(
        element.key == "univariate_overview_preview_vlines" for element in app.text_input
    )
    assert any(
        element.key == "univariate_overview_preview_hlines" for element in app.text_input
    )
    assert any(
        element.key == "univariate_overview_preview_vline_color" for element in app.selectbox
    )
    assert any(
        element.key == "univariate_overview_preview_vline_style" for element in app.selectbox
    )
    assert any(
        element.key == "univariate_overview_preview_hline_color" for element in app.selectbox
    )
    assert any(
        element.key == "univariate_overview_preview_hline_style" for element in app.selectbox
    )
    assert any(
        element.key == "univariate_overview_preview_vline_linewidth" for element in app.slider
    )
    assert any(
        element.key == "univariate_overview_preview_hline_linewidth" for element in app.slider
    )
    assert any(
        element.key == "univariate_overview_preview_shade" for element in app.text_input
    )
    assert not any(
        element.key == "univariate_overview_preview_colors" for element in app.text_input
    )
    assert len(
        [element for element in app.selectbox if "series_style" in element.key]
    ) == 6
    assert len(
        [element for element in app.slider if "series_style" in element.key]
    ) == 6
    _by_key(app.checkbox, "univariate_overview_preview_legend").uncheck()
    app.run()
    assert not app.exception
    assert not any(
        element.key == "univariate_overview_preview_legend_bbox_on" for element in app.checkbox
    )
    assert not any(
        element.key == "univariate_overview_preview_legend_labels"
        for element in app.text_input
    )
    hidden_legend_selects = {
        "univariate_overview_preview_legend_loc",
    }
    assert not any(element.key in hidden_legend_selects for element in app.selectbox)
    hidden_legend_inputs = {
        "univariate_overview_preview_legend_cols",
        "univariate_overview_preview_legend_bbox_x",
        "univariate_overview_preview_legend_bbox_y",
    }
    assert not any(
        element.key in hidden_legend_inputs for element in app.number_input
    )


def test_data_overview_renders_hurst_value_for_sufficient_series(monkeypatch):
    """数据概览在有效样本足够时展示实际赫斯特指数。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    app = _open_standalone_univariate_overview(app, _sample_csv())

    hurst_table = next(
        element.value
        for element in app.dataframe
        if list(element.value.columns)
        == ["变量", "赫斯特指数", "有效观测数", "参考解释"]
    )

    assert hurst_table["变量"].tolist() == ["value"]
    assert hurst_table["赫斯特指数"].notna().all()
    assert hurst_table["有效观测数"].tolist() == [60]


def test_select_rows_uses_variable_names_and_data_start(monkeypatch):
    """输入变量名行和数据开始行后，预览使用对应表头与数据。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    app = _open_standalone_univariate_overview(app, _preamble_csv())
    assert any(
        element.key == "univariate_overview_preview_variable_name_row"
        for element in app.number_input
    )
    assert any(
        element.key == "univariate_overview_preview_data_start_row"
        for element in app.number_input
    )
    assert any("数据读取失败" in element.value for element in app.error)

    _by_key(app.number_input, "univariate_overview_preview_variable_name_row").set_value(3)
    app.run()
    _by_key(app.number_input, "univariate_overview_preview_data_start_row").set_value(4)
    app.run()
    assert not app.exception
    time_column = _by_key(app.selectbox, "univariate_overview_preview_time_column")
    assert "date" in time_column.options
    assert time_column.value == "date"

    preview = next(
        element.value
        for element in app.dataframe
        if list(element.value.columns) == ["date", "sales"]
    )
    assert preview.iloc[0]["sales"] == 10
    assert "exog" in _by_key(app.multiselect, "univariate_overview_preview_vars").options

    # 读取设置变化会清除旧数据集，解析失败时不会继续使用旧变量/模型状态。
    _by_key(app.number_input, "univariate_overview_preview_variable_name_row").set_value(2)
    app.run()
    assert not app.exception
    assert any(
        "数据读取失败" in element.value or "数据集校验失败" in element.value
        for element in app.error
    )
    assert not any(
        element.key == "sarimax_target_select" for element in app.selectbox
    )


def test_time_column_options_refresh_after_variable_name_row_changes(monkeypatch):
    """变量名行变化后，时间列选项必须同步使用新表头。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    app = _open_standalone_univariate_overview(app, _changing_header_csv())

    _by_key(app.number_input, "univariate_overview_preview_variable_name_row").set_value(2)
    app.run()
    _by_key(app.number_input, "univariate_overview_preview_data_start_row").set_value(3)
    app.run()
    time_column = _by_key(app.selectbox, "univariate_overview_preview_time_column")
    assert "old_date" in time_column.options
    assert "new_date" not in time_column.options

    _by_key(app.number_input, "univariate_overview_preview_variable_name_row").set_value(5)
    app.run()
    time_column = _by_key(app.selectbox, "univariate_overview_preview_time_column")
    assert "new_date" in time_column.options
    assert "old_date" not in time_column.options


def test_univariate_overview_starts_at_first_valid_value(monkeypatch):
    """单变量图从首个有效值开始，不把前置 0 作为时间序列起点。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    content = (
        b"date,value\n"
        b"2020-01-01,0\n"
        b"2020-02-01,5\n"
        b"2020-03-01,0\n"
    )
    app = _open_standalone_univariate_overview(
        app, ("zeros.csv", content, "text/csv")
    )

    assert not app.exception
    preview = next(
        element.value
        for element in app.dataframe
        if list(element.value.columns) == ["date", "value"]
    )
    # 表格保留原始时间位置，但 0 在概览本地数据集中按缺失处理；
    # 图表会据此从 2020-02-01 的首个有效值开始绘制。
    assert pd.isna(preview.iloc[0]["value"])
    assert preview.iloc[1]["value"] == 5
    assert pd.isna(preview.iloc[2]["value"])


def test_excel_sheet_selection_via_ui(monkeypatch):
    """Excel 多工作表：右侧出现工作表下拉，切换后数据随之更新。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()

    # 构造含两个工作表（不同时间范围）的 Excel
    index_a = pd.date_range("2020-01-01", periods=12, freq="MS")
    index_b = pd.date_range("2022-01-01", periods=12, freq="MS")
    with pd.ExcelWriter(
        PROJECT_ROOT / "tests" / "models" / "_sheet_sample.xlsx",
        engine="openpyxl",
    ) as writer:
        pd.DataFrame(
            {"date": index_a.strftime("%Y-%m-%d"), "value": range(12)}
        ).to_excel(writer, sheet_name="一表", index=False)
        pd.DataFrame(
            {"date": index_b.strftime("%Y-%m-%d"), "value": range(12, 24)}
        ).to_excel(writer, sheet_name="二表", index=False)

    path = PROJECT_ROOT / "tests" / "models" / "_sheet_sample.xlsx"
    try:
        app = _open_standalone_univariate_overview(
            app,
            (
                "sheet_sample.xlsx",
                path.read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        )
        assert not app.exception

        # 多工作表 → 出现「选择工作表」下拉，默认第一个工作表
        sheet_box = _by_key(app.selectbox, "univariate_overview_preview_sheet")
        assert list(sheet_box.options) == ["一表", "二表"]
        assert sheet_box.value == "一表"
        preview = next(
            element.value
            for element in app.dataframe
            if list(element.value.columns) == ["date", "value"]
        )
        assert preview.iloc[0]["date"] == "2020-01-01"

        # 切换到第二个工作表 → 预览表时间范围变为 2022 起
        _by_key(app.selectbox, "univariate_overview_preview_sheet").select("二表")
        app.run()
        assert not app.exception
        preview = next(
            element.value
            for element in app.dataframe
            if list(element.value.columns) == ["date", "value"]
        )
        assert preview.iloc[0]["date"] == "2022-01-01"
    finally:
        path.unlink(missing_ok=True)


def test_model_target_variables_follow_restored_visible_sheet(monkeypatch, tmp_path):
    """页面恢复工作表控件时，目标变量必须来自可见工作表。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _navigate_to_sarimax(app)

    path = tmp_path / "sheet-targets.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(
            {
                "monthly_date": pd.date_range("2020-01-01", periods=3, freq="D"),
                "monthly_target": [1, 2, 3],
            }
        ).to_excel(writer, sheet_name="月表", index=False)
        pd.DataFrame(
            {
                "daily_date": pd.date_range("2020-01-01", periods=3, freq="D"),
                "daily_target": [4, 5, 6],
            }
        ).to_excel(writer, sheet_name="日表", index=False)

    payload = (
        path.name,
        path.read_bytes(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    _by_key(
        app.file_uploader, "model_analysis.sarimax.upload.uploader"
    ).upload(*payload)
    app.run()
    assert not app.exception
    _by_key(app.button, "sarimax_start_processing_button").click()
    app.run()
    assert not app.exception
    assert "monthly_target" in _by_key(
        app.selectbox, "sarimax_target_select"
    ).options

    # 模拟页面交接快照只恢复了可见工作表控件，底层数据源仍停留在月表。
    app.session_state["sarimax_model_preview_sheet"] = "日表"
    app.run()
    assert not app.exception
    sheet_box = _by_key(app.selectbox, "sarimax_model_preview_sheet")
    assert sheet_box.value == "日表"
    assert not any(
        element.key == "sarimax_target_select" for element in app.selectbox
    )
    time_box = _by_key(app.selectbox, "sarimax_model_preview_time_column")
    assert "daily_date" in time_box.options
    assert "monthly_date" not in time_box.options

    _by_key(app.button, "sarimax_start_processing_button").click()
    app.run()
    assert not app.exception
    target_box = _by_key(app.selectbox, "sarimax_target_select")
    assert target_box.options == ["daily_target"]
    assert target_box.value == "daily_target"


@pytest.mark.parametrize("model_prefix", ["rdl", "ardl"])
def test_model_target_variables_follow_selected_sheet_across_model_tabs(
    monkeypatch, tmp_path, model_prefix
):
    """RDL 和 ARDL 也必须按各自页面的工作表生成目标变量。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    path = tmp_path / f"{model_prefix}-sheet-targets.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(
            {
                "first_date": pd.date_range("2020-01-01", periods=3, freq="D"),
                "first_target": [1, 2, 3],
                "first_exog": [7, 8, 9],
            }
        ).to_excel(writer, sheet_name="第一表", index=False)
        pd.DataFrame(
            {
                "second_date": pd.date_range("2021-01-01", periods=3, freq="D"),
                "second_target": [4, 5, 6],
                "second_exog": [10, 11, 12],
            }
        ).to_excel(writer, sheet_name="第二表", index=False)

    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _prepare_model_app(
        app,
        (
            path.name,
            path.read_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        model_prefix=model_prefix,
    )
    target_key = f"{model_prefix}_target_select"
    exog_key = f"{model_prefix}_exog_select"
    sheet_key = f"{model_prefix}_model_preview_sheet"
    assert _by_key(app.selectbox, target_key).options == [
        "first_target",
        "first_exog",
    ]
    assert _by_key(app.multiselect, exog_key).options == ["first_exog"]
    assert _by_key(app.slider, f"{model_prefix}_train_forecast_window")

    _by_key(app.selectbox, sheet_key).select("第二表")
    app.run()
    assert not app.exception
    assert not any(item.key == target_key for item in app.selectbox)
    assert not any(item.key == exog_key for item in app.multiselect)
    assert not any(
        item.key == f"{model_prefix}_train_forecast_window" for item in app.slider
    )
    time_box = _by_key(app.selectbox, f"{model_prefix}_model_preview_time_column")
    assert "second_date" in time_box.options
    assert "first_date" not in time_box.options

    _by_key(app.button, f"{model_prefix}_start_processing_button").click()
    app.run()
    assert not app.exception
    assert _by_key(app.selectbox, target_key).options == [
        "second_target",
        "second_exog",
    ]
    assert _by_key(app.multiselect, exog_key).options == ["second_exog"]
    assert _by_key(app.slider, f"{model_prefix}_train_forecast_window")


def test_handoff_parse_failure_clears_restored_model_results(monkeypatch):
    """交接后的数据解析失败时，不得继续展示恢复的模型结果。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=90).run()
    _prepare_model_app(app, _sample_csv())
    _by_key(app.button, "sarimax_fit_button").click()
    app.run()
    assert not app.exception
    assert app.session_state["model_analysis.sarimax.fitted_result"] is not None

    # 模拟独立页交接后原始行读取失败：数据集为空但旧结果仍在状态中。
    app.session_state["model_analysis.sarimax.dataset"] = None
    app.session_state["model_analysis.sarimax.upload.raw_rows"] = []
    app.session_state["model_analysis.sarimax.handoff_restore"] = True
    app.run()

    assert not app.exception
    assert app.session_state["model_analysis.sarimax.fitted_result"] is None
    assert app.session_state["model_analysis.sarimax.fit_signature"] is None
    assert app.session_state["model_analysis.sarimax.forecast"] is None
    assert not any(
        item.key == "sarimax_target_select" for item in app.selectbox
    )


def test_time_column_change_clears_model_input_until_reprocessed(monkeypatch):
    """时间列变化后，目标、外生变量和训练范围必须等待重新处理。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    dates = pd.date_range("2020-01-01", periods=60, freq="D")
    frame = pd.DataFrame(
        {
            "date_a": dates,
            "date_b": dates + pd.Timedelta(days=1),
            "value": [10.0 + step * 0.1 for step in range(60)],
            "policy": [1.0 + step * 0.05 for step in range(60)],
        }
    )
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=90).run()
    _prepare_model_app(
        app,
        ("two-time-columns.csv", frame.to_csv(index=False).encode("utf-8"), "text/csv"),
    )
    assert _by_key(app.selectbox, "sarimax_target_select").options == [
        "value",
        "policy",
    ]
    assert _by_key(app.multiselect, "sarimax_exog_select").options == [
        "policy"
    ]
    assert _by_key(app.slider, "sarimax_train_forecast_window")

    _by_key(app.selectbox, "sarimax_model_preview_time_column").select("date_b")
    app.run()

    assert not app.exception
    assert not any(
        item.key == "sarimax_target_select" for item in app.selectbox
    )
    assert not any(item.key == "sarimax_exog_select" for item in app.multiselect)
    assert not any(
        item.key == "sarimax_train_forecast_window" for item in app.slider
    )

    _by_key(app.button, "sarimax_start_processing_button").click()
    app.run()
    assert _by_key(app.selectbox, "sarimax_target_select").options == [
        "value",
        "policy",
    ]


def test_preprocessing_change_clears_model_input_until_reprocessed(monkeypatch):
    """预处理规则变化后，旧目标变量必须等待重新处理。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=90).run()
    _prepare_model_app(app, _sample_csv())
    assert _by_key(app.selectbox, "sarimax_target_select").options == ["value"]

    _by_key(app.multiselect, "sarimax_data_preprocessing").set_value([])
    app.run()

    assert not app.exception
    assert not any(
        item.key == "sarimax_target_select" for item in app.selectbox
    )
    _by_key(app.button, "sarimax_start_processing_button").click()
    app.run()
    assert _by_key(app.selectbox, "sarimax_target_select").options == ["value"]


def test_uae_workbook_target_variables_follow_selected_sheet(monkeypatch):
    """真实 UAE 工作簿中，日度页不能出现月度目标变量。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    workbook = PROJECT_ROOT / "data" / "UAE" / "阿联酋.xlsx"
    assert workbook.exists()
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=90).run()
    _navigate_to_sarimax(app)
    _by_key(
        app.file_uploader, "model_analysis.sarimax.upload.uploader"
    ).upload(
        workbook.name,
        workbook.read_bytes(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    app.run()
    assert not app.exception

    sheet_key = "sarimax_model_preview_sheet"
    _by_key(app.selectbox, sheet_key).select("月度_Wind")
    app.run()
    _by_key(
        app.number_input, "sarimax_model_preview_variable_name_row"
    ).set_value(2)
    app.run()
    _by_key(app.number_input, "sarimax_model_preview_data_start_row").set_value(7)
    app.run()
    _by_key(app.selectbox, "sarimax_model_preview_time_column").select("指标名称")
    app.run()
    _by_key(app.button, "sarimax_start_processing_button").click()
    app.run()
    assert not app.exception
    monthly_target = "中国:出口金额:阿联酋:当月值"
    assert any(
        str(option).startswith(monthly_target)
        for option in _by_key(app.selectbox, "sarimax_target_select").options
    )

    _by_key(app.selectbox, sheet_key).select("日度_Wind")
    app.run()
    assert not any(
        item.key == "sarimax_target_select" for item in app.selectbox
    )
    _by_key(app.button, "sarimax_start_processing_button").click()
    app.run()
    assert not app.exception
    assert all(
        not str(option).startswith(monthly_target)
        for option in _by_key(app.selectbox, "sarimax_target_select").options
    )
