"""SARIMAX 工作流 - ④ 模型预测环节（样本外预测与置信区间）。"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import streamlit as st
from Ts.TsModels import AutoModelResult

from dashboard.core.ui.utils.chart_legend import render_pyplot_figure
from dashboard.explore.analysis.stationarity import matplotlib_date_compatibility
from dashboard.models.SARIMAX.core.modeling import (
    build_prediction_table,
    future_dates,
    produce_forecast,
    translate_ts_error,
)
from dashboard.models.SARIMAX.ui.state import state

logger = logging.getLogger(__name__)


def render_forecast_section(st_obj) -> None:
    """配置预测参数并生成样本外预测。"""
    st_obj.markdown("#### ④ 模型预测")
    result = state.get("fitted_result")
    if result is None:
        st_obj.info("完成「② 模型训练」后可生成样本外预测。")
        return
    best = result.best_result if isinstance(result, AutoModelResult) else result

    control_columns = st_obj.columns(3)
    with control_columns[0]:
        steps = st_obj.number_input(
            "预测期数",
            1,
            36,
            12,
            key="sarimax_forecast_steps",
        )
    with control_columns[1]:
        alpha = st_obj.selectbox(
            "置信水平",
            options=(0.01, 0.05, 0.10),
            index=1,
            format_func=lambda value: f"{1 - value:.0%} 置信区间",
            key="sarimax_forecast_alpha",
        )
    with control_columns[2]:
        dynamic = st_obj.checkbox(
            "动态预测（用自身预测值递推）",
            key="sarimax_forecast_dynamic",
            help="关闭时为一步预测递推，通常区间更窄。",
        )

    future_exog = None
    exog_names = best.exog_names
    if exog_names:
        future_exog = _render_future_exog_editor(st_obj, best, int(steps), exog_names)

    signature = (
        state.get("fit_signature"),
        int(steps),
        float(alpha),
        bool(dynamic),
    )
    if st_obj.button(
        "生成预测",
        type="primary",
        key="sarimax_forecast_button",
        disabled=future_exog is not None and bool(future_exog.isna().any().any()),
    ):
        try:
            with st_obj.spinner("正在调用 Ts 包生成预测..."):
                forecast = produce_forecast(
                    best,
                    steps=int(steps),
                    alpha=float(alpha),
                    dynamic=bool(dynamic),
                    future_exog=future_exog,
                )
        except Exception as exc:  # noqa: BLE001 - 统计预测失败边界
            st_obj.error(translate_ts_error(exc))
            logger.exception("SARIMAX 预测失败")
            return
        state.set("forecast", forecast)
        state.set("forecast_signature", signature)

    forecast = state.get("forecast")
    if forecast is None or state.get("forecast_signature") != signature:
        return

    table = build_prediction_table(forecast)
    # 日期索引转为字符串列显示：Streamlit 1.61 前端 statistics 对
    # datetime 列存在单位换算 bug（min 显示为错误年份），字符串列走
    # 文本统计显示正确日期；CSV 下载仍用原始表格（保留日期类型）。
    display = table.reset_index()
    if "日期" in display.columns:
        display["日期"] = display["日期"].dt.strftime("%Y-%m-%d")
    st_obj.markdown("**预测结果**")
    st_obj.dataframe(display, width="stretch")
    st_obj.download_button(
        "下载预测结果 CSV",
        data=table.to_csv(encoding="utf-8-sig").encode("utf-8-sig"),
        file_name=f"SARIMAX_预测_{int(steps)}期.csv",
        mime="text/csv",
        key="sarimax_forecast_download",
    )
    _render_forecast_chart(st_obj, best, forecast)


def _render_future_exog_editor(st_obj, best, steps: int, exog_names) -> pd.DataFrame:
    """渲染未来外生变量录入编辑器并返回编辑后的数据框。"""
    st_obj.markdown("**未来外生变量**")
    st_obj.caption(
        "模型包含外生变量，请为每个预测期填写全部外生变量的未来值"
        f"（共 {steps} 期，列名须与建模时一致）。"
    )
    index = future_dates(best, steps)
    if index is None:
        # 无日期模型按位置对齐：以第 1 期起标记未来行
        # （Ts 的 _validate_scenario_index 接受任意起点的 RangeIndex）。
        index = pd.RangeIndex(1, steps + 1)
    editor_frame = pd.DataFrame(
        np.nan,
        index=index,
        columns=list(exog_names),
    )
    edited = st_obj.data_editor(
        editor_frame,
        key="sarimax_future_exog_editor",
        num_rows="fixed",
    )
    if edited.isna().any().any():
        missing = int(edited.isna().sum().sum())
        st_obj.warning(f"还有 {missing} 个外生变量值未填写，填写完整后才能预测。")
    return edited


def _render_forecast_chart(st_obj, best, forecast) -> None:
    """绘制历史值与预测均值/置信区间图。"""
    try:
        import matplotlib.pyplot as plt

        with matplotlib_date_compatibility():
            figure, axis = plt.subplots(figsize=(10, 5))
            history = np.asarray(best.data, dtype=float)
            if best.dates is not None:
                x_history = best.dates
                x_future = forecast["dates"]
            else:
                # 无日期模型按期数标记：历史第 1..n 期、预测第 n+1..n+steps 期，
                # 与预测表的「期数」列语义一致（不再从 0 开始）。
                x_history = np.arange(1, len(history) + 1)
                x_future = np.arange(
                    len(history) + 1,
                    len(history) + 1 + len(forecast["mean"]),
                )
            axis.plot(
                x_history,
                history,
                label="历史值",
                color="#1f77b4",
                linewidth=1.5,
            )
            axis.plot(
                x_future,
                forecast["mean"],
                label="预测均值",
                color="#d62728",
                linewidth=2.0,
            )
            axis.fill_between(
                x_future,
                forecast["lower"],
                forecast["upper"],
                color="#d62728",
                alpha=0.2,
                label=f"{1 - forecast['alpha']:.0%} 置信区间",
            )
            axis.legend(frameon=False)
            axis.set_title("SARIMAX 样本外预测")
            figure.tight_layout()
            render_pyplot_figure(st_obj, figure)
    except Exception as exc:  # noqa: BLE001 - 可选图表边界
        st_obj.warning(f"预测图无法绘制：{exc}")
        logger.warning("SARIMAX 预测图绘制失败", exc_info=True)


__all__ = ["render_forecast_section"]
