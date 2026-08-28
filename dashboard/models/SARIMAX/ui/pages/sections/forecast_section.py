"""SARIMAX 工作流 - ③ 模型预测环节（样本外预测与置信区间）。"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from Ts.TsModels import AutoARDLResult, AutoModelResult

from dashboard.core.ui.utils.chart_legend import render_pyplot_figure
from dashboard.core.ui.utils.matplotlib_compat import matplotlib_date_compatibility
from dashboard.core.workspace import stable_signature
from data_overview.core.dataset import numeric_variable_names
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
    st_obj.markdown("#### ③ 模型预测")
    result = state.get("fitted_result")
    if result is None:
        st_obj.info("完成「① 模型训练」后可生成样本外预测。")
        return
    best = (
        result.best_result
        if isinstance(result, (AutoModelResult, AutoARDLResult))
        else result
    )
    family = state.get("model_selection", ("SARIMAX", "手动配置"))[0]
    dataset = state.get("dataset")

    control_columns = st_obj.columns(3)
    with control_columns[0]:
        start = st_obj.number_input(
            "预测起点（位置）",
            min_value=0,
            value=int(best.nobs),
            step=1,
            key="sarimax_forecast_start",
            help="按 Ts 的零基位置填写；样本外预测通常从拟合样本末期位置开始。",
        )
    with control_columns[1]:
        end = st_obj.number_input(
            "预测终点（位置）",
            min_value=0,
            value=int(best.nobs + 11),
            step=1,
            key="sarimax_forecast_end",
            help="包含该位置；必须不小于预测起点。",
        )
    with control_columns[2]:
        alpha = st_obj.selectbox(
            "置信水平",
            options=(0.01, 0.05, 0.10),
            index=1,
            format_func=lambda value: f"{1 - value:.0%} 置信区间",
            key="sarimax_forecast_alpha",
        )

    dynamic = st_obj.checkbox(
        "动态预测（用自身预测值递推）",
        key="sarimax_forecast_dynamic",
        help="传递给 Ts 的 dynamic 参数；纯样本外窗口本身已经采用递推。",
    )

    start = int(start)
    end = int(end)
    if start < int(best.nobs):
        st_obj.warning(f"预测起点不能早于样本外位置 {best.nobs}。")
        return
    if end < start:
        st_obj.warning("预测终点不能早于预测起点。")
        return
    total_steps = end - int(best.nobs) + 1

    future_exog = None
    exog_names = tuple(best.exog_names)
    source_columns: tuple[str, ...] = ()
    if exog_names:
        future_exog, source_columns = _render_future_exog_editor(
            st_obj,
            dataset,
            best,
            total_steps,
            exog_names,
        )

    signature = stable_signature(
        {
            "fit_signature": state.get("fit_signature"),
            "start": start,
            "end": end,
            "alpha": float(alpha),
            "dynamic": bool(dynamic),
            "source_columns": source_columns,
            "future_exog": _serialise_frame(future_exog),
        }
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
                    alpha=float(alpha),
                    dynamic=bool(dynamic),
                    future_exog=future_exog,
                    start=start,
                    end=end,
                )
        except Exception as exc:
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
        file_name=f"{family}_预测_{int(forecast['steps'])}期.csv",
        mime="text/csv",
        key="sarimax_forecast_download",
    )
    _render_forecast_chart(st_obj, best, forecast, family=family)


def _render_future_exog_editor(
    st_obj,
    dataset,
    best,
    total_steps: int,
    exog_names: tuple[str, ...],
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """从数据集预填未来外生路径，并允许用户选择来源列及编辑数值。"""
    numeric = [] if dataset is None else numeric_variable_names(dataset.frame)
    if not numeric:
        st_obj.error("当前数据表没有可用的数值列，无法提供未来外生变量路径。")
        empty = pd.DataFrame(
            np.nan,
            index=_future_index(best, total_steps),
            columns=exog_names,
        )
        return empty, ()
    source_columns = []
    for position, model_name in enumerate(exog_names):
        default = (
            model_name
            if model_name in numeric
            else (numeric[0] if numeric else None)
        )
        selected = st_obj.selectbox(
            f"{model_name} 的未来值来源",
            options=numeric,
            index=numeric.index(default) if default in numeric else 0,
            key=f"sarimax_future_exog_source_{position}",
            help="从当前数据表选择该模型外生变量的未来路径。",
        )
        source_columns.append(selected)
    source_columns = tuple(source_columns)
    if not source_columns:
        empty = pd.DataFrame(
            np.nan,
            index=_future_index(best, total_steps),
            columns=exog_names,
        )
        return empty, source_columns

    editor_frame = _future_exog_from_dataset(
        dataset,
        best,
        total_steps,
        source_columns,
        exog_names,
    )
    editor_signature = stable_signature(
        {
            "start": int(best.nobs),
            "steps": total_steps,
            "sources": source_columns,
            "index": [str(value) for value in editor_frame.index],
        }
    )
    if state.get("future_exog_editor_signature") != editor_signature:
        st_obj.session_state.pop("sarimax_future_exog_editor", None)
        state.set("future_exog_editor_signature", editor_signature)
    st_obj.markdown("**未来外生变量路径**")
    st_obj.caption("默认从当前数据表提取；空值可直接在下表补录。")
    edited = st_obj.data_editor(
        editor_frame,
        key="sarimax_future_exog_editor",
        num_rows="fixed",
    )
    return edited.astype(float), source_columns


def _future_exog_from_dataset(
    dataset,
    best,
    total_steps: int,
    source_columns: tuple[str, ...],
    exog_names: tuple[str, ...],
) -> pd.DataFrame:
    """按拟合结果的未来日历从当前数据框提取外生变量路径。"""
    if dataset is None:
        return pd.DataFrame(
            np.nan,
            index=_future_index(best, total_steps),
            columns=exog_names,
        )
    frame = dataset.frame.copy()
    if dataset.time_column is not None:
        dates = pd.DatetimeIndex(pd.to_datetime(frame[dataset.time_column]))
        frame = frame.drop(columns=[dataset.time_column])
        frame.index = dates
        frame = frame.sort_index()
        index = future_dates(best, total_steps)
        if index is None:
            index = pd.RangeIndex(total_steps)
        values = {
            model_name: pd.to_numeric(frame[source], errors="coerce").reindex(index)
            for model_name, source in zip(exog_names, source_columns)
        }
        return pd.DataFrame(values, index=index)

    index = _future_index(best, total_steps)
    values = {}
    for model_name, source in zip(exog_names, source_columns):
        series = pd.to_numeric(frame[source], errors="coerce")
        values[model_name] = series.iloc[
            int(best.nobs) : int(best.nobs) + total_steps
        ].to_numpy()
    return pd.DataFrame(values, index=index)


def _future_index(best, total_steps: int) -> pd.Index:
    """返回与 Ts 未来路径兼容的编辑器索引。"""
    dates = future_dates(best, total_steps)
    return dates if dates is not None else pd.RangeIndex(total_steps)


def _serialise_frame(frame: pd.DataFrame | None):
    """把外生变量表转换为稳定签名支持的基础类型。"""
    if frame is None:
        return None
    values = frame.astype(object).where(frame.notna(), None).values.tolist()
    return {"columns": [str(column) for column in frame.columns], "values": values}


def _render_forecast_chart(st_obj, best, forecast, *, family: str) -> None:
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
                    int(forecast.get("start", len(history))) + 1,
                    int(forecast.get("start", len(history)))
                    + 1
                    + len(forecast["mean"]),
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
            axis.set_title(f"{family} 样本外预测")
            figure.tight_layout()
            render_pyplot_figure(st_obj, figure)
    except Exception as exc:
        st_obj.warning(f"预测图无法绘制：{exc}")
        logger.warning("SARIMAX 预测图绘制失败", exc_info=True)


__all__ = ["render_forecast_section"]
