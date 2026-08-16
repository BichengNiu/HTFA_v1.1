"""SARIMAX UI 端到端流程测试（AppTest 驱动完整工作流）。"""

from __future__ import annotations

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


def _by_key(elements, key: str):
    return next(element for element in elements if element.key == key)


def test_full_workflow_via_ui(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("HTFA_DEBUG_MODE", "true")
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=60).run()
    _navigate_to_sarimax(app)

    # 导航结果：单 tab「SARIMAX 模型」，页内四环节标题与引导信息齐全
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["SARIMAX 模型"]
    title_texts = " ".join(element.value for element in app.markdown)
    assert "① 数据概览" in title_texts
    assert "② 模型训练" in title_texts
    assert "③ 模型分析" in title_texts
    assert "④ 模型预测" in title_texts
    info_texts = " ".join(element.value for element in app.info)
    assert "请在上方上传数据文件" in info_texts
    assert "完成「① 数据概览」（在上方上传数据）后可配置并拟合模型" in info_texts
    assert "完成「② 模型训练」后可查看模型分析结果" in info_texts

    # ① 数据概览：上传文件后出现数据表格与预览绘图（compact 模式
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
    _by_key(app.radio, "sarimax_mode_radio").set_value(
        "自动选阶（AutoSARIMAX）"
    )
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


def test_data_table_options_via_ui(monkeypatch):
    """数据表高级选项：视图开关互斥、筛选直接作用于预览表、统计量。"""
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

    # 两个高级选项 expander 并排：数据表在前，图形在后
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

    # 展开数据表高级选项后出现视图开关与筛选控件
    app.expander[0].expanded = True
    app.run()
    assert not app.exception
    head_box = _by_key(app.checkbox, "sarimax_table_view_head")
    tail_box = _by_key(app.checkbox, "sarimax_table_view_tail")
    assert head_box.value is True
    assert tail_box.value is False
    _by_key(app.selectbox, "sarimax_table_filter_col")
    _by_key(app.selectbox, "sarimax_table_filter_op")
    _by_key(app.number_input, "sarimax_table_filter_val")
    # 月度数据 → 时间筛选按频率渲染为「时间范围」预设下拉
    # （无 date_input；自定义时才出现起止年月下拉）
    _by_key(app.selectbox, "sarimax_table_time_preset")
    assert not app.date_input
    assert not any(
        element.key == "sarimax_table_view_reset" for element in app.checkbox
    )

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

    # 视图开关互斥：清除数值筛选后勾选「显示尾10行」→ 头10行自动取消
    # （每次交互前重新获取元素，AppTest 树在多次 rerun 后旧引用失效）
    _by_key(app.selectbox, "sarimax_table_filter_col").select("无")
    app.run()
    _by_key(app.checkbox, "sarimax_table_view_tail").check()
    app.run()
    assert not app.exception
    assert _by_key(app.checkbox, "sarimax_table_view_tail").value is True
    assert _by_key(app.checkbox, "sarimax_table_view_head").value is False
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

    # 清除尾10行视图 + 时间范围回「全部」→ 头/尾均未勾选 = 显示全部
    _by_key(app.checkbox, "sarimax_table_view_tail").uncheck()
    _by_key(app.selectbox, "sarimax_table_time_preset").select("全部")
    app.run()
    assert not app.exception
    assert len(preview_frame()) == 60
    # 重新勾选头10行 → 恢复默认前 10 行视图
    _by_key(app.checkbox, "sarimax_table_view_head").check()
    app.run()
    assert not app.exception
    assert len(preview_frame()) == 10
    assert preview_frame().iloc[0]["date"] == "2020-01-01"


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
