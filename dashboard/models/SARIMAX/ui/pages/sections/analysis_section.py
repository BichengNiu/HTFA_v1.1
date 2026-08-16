"""SARIMAX 工作流 - ③ 模型分析环节（参数、拟合、诊断）。"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st
from Ts.TsModels import AutoModelResult

from dashboard.core.ui.utils.chart_legend import render_pyplot_figure
from dashboard.explore.analysis.stationarity import matplotlib_date_compatibility
from dashboard.models.SARIMAX.core.modeling import run_residual_diagnostics
from dashboard.models.SARIMAX.ui.state import state

logger = logging.getLogger(__name__)

_DEFAULT_LAGS = 10


def render_analysis_section(st_obj) -> None:
    """展示已拟合模型的参数、拟合图、诊断图与残差检验。"""
    st_obj.markdown("#### ③ 模型分析")
    result = state.get("fitted_result")
    if result is None:
        st_obj.info("完成「② 模型训练」后可查看模型分析结果。")
        return
    best = result.best_result if isinstance(result, AutoModelResult) else result

    _render_parameter_table(st_obj, best)

    st_obj.markdown("**拟合效果图**")
    try:
        with matplotlib_date_compatibility():
            figure, _ = best.plot_fit()
            render_pyplot_figure(st_obj, figure)
    except Exception as exc:  # noqa: BLE001 - 可选图表边界
        st_obj.warning(f"拟合效果图无法绘制：{exc}")
        logger.warning("SARIMAX 拟合图绘制失败", exc_info=True)

    st_obj.markdown("**残差诊断图**")
    try:
        with matplotlib_date_compatibility():
            figure, _ = best.plot_diagnostics()
            render_pyplot_figure(st_obj, figure)
    except Exception as exc:  # noqa: BLE001 - 可选图表边界
        st_obj.warning(f"残差诊断图无法绘制：{exc}")
        logger.warning("SARIMAX 诊断图绘制失败", exc_info=True)

    _render_residual_tests(st_obj, best)
    _render_root_conditions(st_obj, best)


def _render_parameter_table(st_obj, best) -> None:
    """展示参数估计表（估计值/标准误/P 值）。"""
    st_obj.markdown("**参数估计**")
    rows = [
        {
            "参数": name,
            "估计值": best.params[name],
            "标准误": best.std_errors[name],
            "P值": best.p_values[name],
        }
        for name in best.params
    ]
    st_obj.dataframe(pd.DataFrame(rows), width="stretch")
    st_obj.caption(
        "P 值基于所选协方差估计（cov_type）计算；外生变量参数名与数据列名一致。"
    )


def _render_residual_tests(st_obj, best) -> None:
    """运行并展示残差诊断检验（Ljung-Box / 正态性 / ARCH）。"""
    st_obj.markdown("**残差诊断检验**")
    control_columns = st_obj.columns(2)
    with control_columns[0]:
        lags = st_obj.number_input(
            "检验滞后阶数",
            1,
            30,
            _DEFAULT_LAGS,
            key="sarimax_diag_lags",
            help="Ljung-Box 与 Engle LM 检验使用的最大滞后阶数。",
        )
    signature = (state.get("fit_signature"), int(lags))
    with control_columns[1]:
        run_clicked = st_obj.button(
            "运行残差检验",
            key="sarimax_diag_button",
        )
    if run_clicked:
        try:
            with st_obj.spinner("正在调用 Ts 包执行残差检验..."):
                table = run_residual_diagnostics(best, lags=int(lags))
        except Exception as exc:  # noqa: BLE001 - 统计检验失败边界
            st_obj.error(f"残差检验无法执行：{exc}")
            logger.exception("SARIMAX 残差检验失败")
            state.set("diagnostics_table", None)
            state.set("diagnostics_signature", None)
            return
        state.set("diagnostics_table", table)
        state.set("diagnostics_signature", signature)

    table = state.get("diagnostics_table")
    if table is None or state.get("diagnostics_signature") != signature:
        return
    st_obj.dataframe(table, width="stretch")
    st_obj.download_button(
        "下载检验结果",
        data=table.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
        file_name="SARIMAX_残差检验.csv",
        mime="text/csv",
        key="sarimax_diag_download",
    )


def _render_root_conditions(st_obj, best) -> None:
    """展示 AR/MA 根与平稳性/可逆性结论。"""
    if not hasattr(best, "is_stationary") or not hasattr(best, "is_invertible"):
        return
    st_obj.markdown("**模型稳定性**")
    stationary = best.is_stationary
    invertible = best.is_invertible
    columns = st_obj.columns(2)
    columns[0].metric(
        "AR 平稳性",
        "平稳" if stationary else "非平稳",
        delta=None,
        delta_color="off",
    )
    columns[1].metric(
        "MA 可逆性",
        "可逆" if invertible else "不可逆",
        delta=None,
        delta_color="off",
    )
    if not stationary or not invertible:
        st_obj.warning(
            "模型存在位于单位圆上或圆内的根，拟合结果可能不稳定，"
            "建议调整差分阶数或季节项后再拟合。"
        )


__all__ = ["render_analysis_section"]
