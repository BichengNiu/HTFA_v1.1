"""SARIMAX UI 端到端流程测试（AppTest 驱动完整工作流）。"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
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


def _by_key(elements, key: str):
    return next(element for element in elements if element.key == key)


def test_full_workflow_via_ui(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _navigate_to_sarimax(app)

    # 导航结果：单 tab「动态回归模型」，页内四环节标题与引导信息齐全
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["动态回归模型"]
    title_texts = " ".join(element.value for element in app.markdown)
    assert "① 数据预览" in title_texts
    assert "② 模型训练" in title_texts
    assert "③ 模型分析" in title_texts
    assert "④ 模型预测" in title_texts
    info_texts = " ".join(element.value for element in app.info)
    assert "请在上方上传数据文件" in info_texts
    assert "完成「① 数据预览」（在上方上传数据）后可配置并拟合模型" in info_texts
    assert "完成「② 模型训练」后可查看模型分析结果" in info_texts

    # ① 数据预览：上传文件后出现数据表格与预览绘图（compact 模式
    # 不再显示「已加载」success 与行数小字）
    app.file_uploader[0].upload(*_sample_csv())
    app.run()
    assert not app.exception
    assert not app.success
    assert any(
        element.key == "sarimax_preview_vars" for element in app.multiselect
    )
    # 时间序列预览图只渲染一次（回归：expander 下方不应出现重复图）
    assert len(app.image) == 1
    assert any(element.key == "sarimax_target_select" for element in app.selectbox)

    # ② 模型训练：默认手动配置 (1,0,1)，拟合按钮可用并执行
    fit_button = _by_key(app.button, "sarimax_fit_button")
    assert not fit_button.disabled
    fit_button.click()
    app.run()
    assert not app.exception
    metrics = {element.label: element.value for element in app.metric}
    assert "AIC" in metrics and "BIC" in metrics and "对数似然" in metrics
    assert any("已收敛" in element.value for element in app.success)

    # ③ 模型分析：残差检验运行后出现结果表与下载按钮
    _by_key(app.button, "sarimax_diag_button").click()
    app.run()
    assert not app.exception
    assert any("残差自相关" in str(element.value) for element in app.dataframe)
    assert any(element.key == "sarimax_diag_download" for element in app.download_button)

    # ④ 模型预测：生成预测后出现预测表与下载按钮
    forecast_button = _by_key(app.button, "sarimax_forecast_button")
    assert not forecast_button.disabled
    forecast_button.click()
    app.run()
    assert not app.exception
    assert any(
        list(element.value.columns) == ["日期", "预测值", "下界", "上界"]
        or list(element.value.columns) == ["期数", "预测值", "下界", "上界"]
        for element in app.dataframe
    )
    assert any(
        element.key == "sarimax_forecast_download" for element in app.download_button
    )


def test_auto_mode_workflow_via_ui(monkeypatch):
    """自动选阶模式：切换配置方式、缩小搜索范围后拟合出候选表。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _navigate_to_sarimax(app)
    app.file_uploader[0].upload(*_sample_csv())
    app.run()
    assert not app.exception

    # 切换到自动选阶，并把范围缩到 4 个组合
    _by_key(app.segmented_control, "sarimax_config_mode").set_value("自动选阶")
    app.run()
    assert not app.exception
    _by_key(app.number_input, "sarimax_auto_p_max").set_value(1)
    _by_key(app.number_input, "sarimax_auto_q_max").set_value(1)
    _by_key(app.number_input, "sarimax_auto_d_max").set_value(0)
    _by_key(app.number_input, "sarimax_auto_P_max").set_value(0)
    _by_key(app.number_input, "sarimax_auto_Q_max").set_value(0)
    _by_key(app.number_input, "sarimax_auto_D_max").set_value(0)
    app.run()
    assert not app.exception
    assert any("网格搜索将尝试 4 个模型组合" in c.value for c in app.caption)

    fit_button = _by_key(app.button, "sarimax_fit_button")
    assert not fit_button.disabled
    fit_button.click()
    app.run()
    assert not app.exception
    assert any("最优模型" in m.value for m in app.markdown)
    assert any(
        "模型" in element.value.columns for element in app.dataframe
    )
    metrics = {element.label: element.value for element in app.metric}
    assert "AIC" in metrics


def _open_dynamic_family(app, family: str, mode: str) -> None:
    """上传连续多变量样本，切换到指定动态回归模型族。"""
    app.file_uploader[0].upload(*_dynamic_sample_csv())
    app.run()
    _by_key(app.multiselect, "sarimax_exog_select").set_value(["policy"])
    app.run()
    _by_key(app.segmented_control, "sarimax_model_family").set_value(family)
    app.run()
    _by_key(app.segmented_control, "sarimax_config_mode").set_value(mode)
    app.run()
    assert not app.exception


def test_rdl_manual_and_auto_workflows_via_ui(monkeypatch):
    """RDL 两种配置方式均保留输入传递函数并可完成拟合。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=90).run()
    _navigate_to_sarimax(app)
    _open_dynamic_family(app, "RDL", "手动配置")
    assert _by_key(app.dataframe, "sarimax_rdl_input_table")
    _by_key(app.button, "sarimax_fit_button").click()
    app.run()
    assert not app.exception
    assert any("有效样本量" in item.value for item in app.success)

    _by_key(app.segmented_control, "sarimax_config_mode").set_value("自动选阶")
    app.run()
    _by_key(app.number_input, "sarimax_rdl_auto_error_p_max").set_value(1)
    _by_key(app.number_input, "sarimax_rdl_auto_error_d_max").set_value(0)
    _by_key(app.number_input, "sarimax_rdl_auto_error_q_max").set_value(0)
    _by_key(app.number_input, "sarimax_rdl_auto_error_P_max").set_value(0)
    _by_key(app.number_input, "sarimax_rdl_auto_error_D_max").set_value(0)
    _by_key(app.number_input, "sarimax_rdl_auto_error_Q_max").set_value(0)
    app.run()
    _by_key(app.button, "sarimax_fit_button").click()
    app.run()
    assert not app.exception
    assert any("最优模型" in item.value for item in app.markdown)


def test_ardl_manual_and_auto_workflows_via_ui(monkeypatch):
    """ARDL 两种配置方式显示逐变量滞后，不遗留 RDL 控件或旧结果。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=90).run()
    _navigate_to_sarimax(app)
    _open_dynamic_family(app, "ARDL", "手动配置")
    assert _by_key(app.dataframe, "sarimax_ardl_input_table")
    assert not any(
        item.key == "sarimax_rdl_input_table" for item in app.dataframe
    )
    _by_key(app.button, "sarimax_fit_button").click()
    app.run()
    assert not app.exception
    assert any(tab.label == "动态结构" for tab in app.tabs)

    # 切换模型族必须清除旧 ARDL 结果，并且只留下 RDL 控件。
    _by_key(app.segmented_control, "sarimax_model_family").set_value("RDL")
    app.run()
    assert not app.exception
    assert _by_key(app.dataframe, "sarimax_rdl_input_table")
    assert not any(metric.label == "AIC" for metric in app.metric)
    _by_key(app.segmented_control, "sarimax_model_family").set_value("ARDL")
    app.run()
    assert _by_key(app.dataframe, "sarimax_ardl_input_table")

    _by_key(app.segmented_control, "sarimax_config_mode").set_value("自动选阶")
    app.run()
    assert _by_key(app.dataframe, "sarimax_auto_ardl_input_table")
    _by_key(app.number_input, "sarimax_auto_ardl_target_lag").set_value(1)
    app.run()
    _by_key(app.button, "sarimax_fit_button").click()
    app.run()
    assert not app.exception
    assert any("最优 ARDL" in item.value for item in app.markdown)


def test_data_table_options_via_ui(monkeypatch):
    """数据表高级选项：行数、筛选直接作用于预览表、统计量。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _navigate_to_sarimax(app)
    app.file_uploader[0].upload(*_sample_csv())
    app.run()
    assert not app.exception

    # 上传组件与变量选择都渲染在主区域（sidebar 不再有上传器）
    assert not app.sidebar.file_uploader
    assert app.file_uploader
    _by_key(app.multiselect, "sarimax_preview_vars")

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
    view_mode = _by_key(app.selectbox, "sarimax_table_view_mode")
    assert view_mode.value == "显示头10行"
    _by_key(app.selectbox, "sarimax_table_filter_col")
    filter_op = _by_key(app.selectbox, "sarimax_table_filter_op")
    assert "≠" in filter_op.options
    assert _by_key(app.number_input, "sarimax_table_filter_val").label == "值"
    # 月度数据 → 时间筛选按频率渲染为「时间范围」预设下拉
    # （无 date_input；自定义时才出现起止年月下拉）
    _by_key(app.selectbox, "sarimax_table_time_preset")
    assert not app.date_input
    assert not any(element.key == "sarimax_table_view_head" for element in app.checkbox)
    assert not any(element.key == "sarimax_table_view_tail" for element in app.checkbox)

    # 数值筛选：value ≥ 2.0 → 上方预览表直接变为筛选结果（少于 10 行）
    _by_key(app.selectbox, "sarimax_table_filter_col").select("value")
    _by_key(app.number_input, "sarimax_table_filter_val").set_value(2.0)
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
    _by_key(app.selectbox, "sarimax_table_filter_col").select("无")
    app.run()
    _by_key(app.selectbox, "sarimax_table_view_mode").select("显示尾10行")
    app.run()
    assert not app.exception
    assert _by_key(app.selectbox, "sarimax_table_view_mode").value == "显示尾10行"
    # 预览表显示全部数据的最后 10 行（60 行数据末尾为 2024-12）
    tailed = preview_frame()
    assert len(tailed) == 10
    assert tailed.iloc[-1]["date"] == "2024-12-01"

    # 时间预设：月度数据选「过去3个月」→ 最后 3 行（2024-10 ~ 2024-12）
    _by_key(app.selectbox, "sarimax_table_time_preset").select("过去3个月")
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
    _by_key(app.selectbox, "sarimax_table_time_preset").select("自定义")
    app.run()
    assert not app.exception
    assert _by_key(app.selectbox, "sarimax_table_time_start")
    assert _by_key(app.selectbox, "sarimax_table_time_end")
    _by_key(app.selectbox, "sarimax_table_time_start").select("2023-01")
    _by_key(app.selectbox, "sarimax_table_time_end").select("2023-12")
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
    _by_key(app.selectbox, "sarimax_table_view_mode").select("显示全部")
    _by_key(app.selectbox, "sarimax_table_time_preset").select("全部")
    app.run()
    assert not app.exception
    assert len(preview_frame()) == 60
    # 选择指定行数 17 → 显示前 17 行
    _by_key(app.selectbox, "sarimax_table_view_mode").select("显示指定行数")
    app.run()
    assert not app.exception
    _by_key(app.number_input, "sarimax_table_view_rows").set_value(17)
    app.run()
    assert not app.exception
    assert len(preview_frame()) == 17
    assert preview_frame().iloc[0]["date"] == "2020-01-01"


def test_page_level_facet_renders_independent_plots(monkeypatch):
    """分面在 Streamlit 页面中生成多个独立图，而不是单个子图 Figure。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _navigate_to_sarimax(app)
    app.file_uploader[0].upload(*_multi_sample_csv())
    app.run()
    assert not app.exception

    variables = _by_key(app.multiselect, "sarimax_preview_vars")
    variables.set_value(["value_a", "value_b"])
    app.run()
    assert not app.exception
    assert len(app.image) == 1

    _by_key(app.checkbox, "sarimax_preview_facet").check()
    app.run()
    assert not app.exception
    assert len(app.image) == 2
    image_columns = [
        column
        for column in app.columns
        if any(type(child).__name__ == "Image" for child in column.children.values())
    ]
    assert len(image_columns) == 2

    _by_key(app.number_input, "sarimax_preview_facet_cols").set_value(2)
    app.run()
    assert not app.exception
    assert len(app.image) == 2

    app.expander[1].expanded = True
    app.run()
    assert not app.exception
    assert _by_key(app.checkbox, "sarimax_preview_sharex").value is True
    assert _by_key(app.checkbox, "sarimax_preview_sharey").value is False
    assert _by_key(app.checkbox, "sarimax_preview_sharex").proto.disabled
    assert _by_key(app.checkbox, "sarimax_preview_sharey").proto.disabled
    assert _by_key(app.number_input, "sarimax_preview_legend_bbox_x").proto.disabled
    assert _by_key(app.number_input, "sarimax_preview_legend_bbox_y").proto.disabled
    assert _by_key(app.number_input, "sarimax_preview_legend_cols").proto.disabled
    assert _by_key(app.number_input, "sarimax_preview_legend_size")
    _by_key(app.selectbox, "sarimax_preview_legend_loc").select("upper right")
    app.run()
    assert not app.exception
    assert app.expander[1].proto.id
    assert _by_key(app.number_input, "sarimax_preview_legend_bbox_x").proto.disabled
    assert _by_key(app.number_input, "sarimax_preview_legend_bbox_y").proto.disabled
    assert any(
        element.key == "sarimax_preview_grid_style" for element in app.selectbox
    )
    assert any(
        element.key == "sarimax_preview_vlines" for element in app.text_input
    )
    assert any(
        element.key == "sarimax_preview_hlines" for element in app.text_input
    )
    assert any(
        element.key == "sarimax_preview_vline_color" for element in app.selectbox
    )
    assert any(
        element.key == "sarimax_preview_vline_style" for element in app.selectbox
    )
    assert any(
        element.key == "sarimax_preview_hline_color" for element in app.selectbox
    )
    assert any(
        element.key == "sarimax_preview_hline_style" for element in app.selectbox
    )
    assert any(
        element.key == "sarimax_preview_vline_linewidth" for element in app.slider
    )
    assert any(
        element.key == "sarimax_preview_hline_linewidth" for element in app.slider
    )
    assert any(
        element.key == "sarimax_preview_shade" for element in app.text_input
    )
    assert not any(
        element.key == "sarimax_preview_colors" for element in app.text_input
    )
    assert len(
        [element for element in app.selectbox if "series_style" in element.key]
    ) == 6
    assert len(
        [element for element in app.slider if "series_style" in element.key]
    ) == 6
    _by_key(app.checkbox, "sarimax_preview_legend").uncheck()
    app.run()
    assert not app.exception
    assert not any(
        element.key == "sarimax_preview_legend_bbox_on" for element in app.checkbox
    )
    assert not any(
        element.key == "sarimax_preview_legend_labels"
        for element in app.text_input
    )
    hidden_legend_selects = {
        "sarimax_preview_legend_loc",
    }
    assert not any(element.key in hidden_legend_selects for element in app.selectbox)
    hidden_legend_inputs = {
        "sarimax_preview_legend_cols",
        "sarimax_preview_legend_bbox_x",
        "sarimax_preview_legend_bbox_y",
    }
    assert not any(
        element.key in hidden_legend_inputs for element in app.number_input
    )


def test_select_rows_uses_variable_names_and_data_start(monkeypatch):
    """输入变量名行和数据开始行后，预览使用对应表头与数据。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _navigate_to_sarimax(app)
    app.file_uploader[0].upload(*_preamble_csv())
    app.run()
    assert not app.exception
    assert any(
        element.key == "sarimax_preview_variable_name_row"
        for element in app.number_input
    )
    assert any(
        element.key == "sarimax_preview_data_start_row"
        for element in app.number_input
    )
    assert any("数据读取失败" in element.value for element in app.error)

    _by_key(app.number_input, "sarimax_preview_variable_name_row").set_value(3)
    app.run()
    _by_key(app.number_input, "sarimax_preview_data_start_row").set_value(4)
    app.run()
    assert not app.exception
    time_column = _by_key(app.selectbox, "sarimax_preview_time_column")
    assert "date" in time_column.options
    assert time_column.value == "date"

    preview = next(
        element.value
        for element in app.dataframe
        if list(element.value.columns) == ["date", "sales"]
    )
    assert preview.iloc[0]["sales"] == 10
    assert "exog" in _by_key(app.multiselect, "sarimax_preview_vars").options
    target = _by_key(app.selectbox, "sarimax_target_select")
    assert set(target.options) >= {"sales", "exog"}

    # 读取设置变化会清除旧数据集，解析失败时不会继续使用旧变量/模型状态。
    _by_key(app.number_input, "sarimax_preview_variable_name_row").set_value(2)
    app.run()
    assert not app.exception
    assert any(
        "数据读取失败" in element.value or "数据集校验失败" in element.value
        for element in app.error
    )
    assert not any(
        element.key == "sarimax_target_select" for element in app.selectbox
    )


def test_zero_values_are_missing_in_sarimax_preview(monkeypatch):
    """SARIMAX 预览图与预览表都不把数值 0 当作有效观测。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _navigate_to_sarimax(app)
    content = (
        "date,value\n"
        "2020-01-01,0\n"
        "2020-02-01,5\n"
        "2020-03-01,0\n"
    ).encode("utf-8")
    app.file_uploader[0].upload("zeros.csv", content, "text/csv")
    app.run()

    assert not app.exception
    preview = next(
        element.value
        for element in app.dataframe
        if list(element.value.columns) == ["date", "value"]
    )
    assert pd.isna(preview.iloc[0]["value"])
    assert preview.iloc[1]["value"] == 5
    assert pd.isna(preview.iloc[2]["value"])


def test_excel_sheet_selection_via_ui(monkeypatch):
    """Excel 多工作表：右侧出现工作表下拉，切换后数据随之更新。"""
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _navigate_to_sarimax(app)

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
        app.file_uploader[0].upload(
            "sheet_sample.xlsx",
            path.read_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        app.run()
        assert not app.exception

        # 多工作表 → 出现「选择工作表」下拉，默认第一个工作表
        sheet_box = _by_key(app.selectbox, "sarimax_preview_sheet")
        assert list(sheet_box.options) == ["一表", "二表"]
        assert sheet_box.value == "一表"
        preview = next(
            element.value
            for element in app.dataframe
            if list(element.value.columns) == ["date", "value"]
        )
        assert preview.iloc[0]["date"] == "2020-01-01"

        # 切换到第二个工作表 → 预览表时间范围变为 2022 起
        _by_key(app.selectbox, "sarimax_preview_sheet").select("二表")
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
