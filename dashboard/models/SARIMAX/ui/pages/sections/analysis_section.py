"""SARIMAX 工作流 - ③ 模型分析环节（参数、拟合、诊断）。"""

from __future__ import annotations

import logging

import pandas as pd
from Ts.TsModels import AutoARDLResult, AutoModelResult

from dashboard.core.ui.utils.chart_legend import render_pyplot_figure
from dashboard.core.ui.utils.matplotlib_compat import matplotlib_date_compatibility
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
    best = (
        result.best_result
        if isinstance(result, (AutoModelResult, AutoARDLResult))
        else result
    )
    fit_tab, structure_tab, diagnostic_tab = st_obj.tabs(
        ["估计与拟合", "动态结构", "残差诊断"]
    )
    with fit_tab:
        _render_parameter_table(st_obj, best)
        st_obj.markdown("**拟合效果图**")
        try:
            with matplotlib_date_compatibility():
                figure, _ = best.plot_fit()
                render_pyplot_figure(st_obj, figure)
        except Exception as exc:
            st_obj.warning(f"拟合效果图无法绘制：{exc}")
            logger.warning("动态回归拟合图绘制失败", exc_info=True)
    with structure_tab:
        _render_dynamic_structure(st_obj, best)
    with diagnostic_tab:
        st_obj.markdown("**残差诊断图**")
        try:
            with matplotlib_date_compatibility():
                figure, _ = best.plot_diagnostics()
                render_pyplot_figure(st_obj, figure)
        except Exception as exc:
            st_obj.warning(f"残差诊断图无法绘制：{exc}")
            logger.warning("动态回归诊断图绘制失败", exc_info=True)
        _render_residual_tests(st_obj, best)


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
        except Exception as exc:
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


def _render_dynamic_structure(st_obj, best) -> None:
    """按模型族展示传递函数、ARDL 滞后或 SARIMAX 根结构。"""
    distributed = getattr(best, "distributed_lags", {})
    if distributed:
        if isinstance(distributed, dict) and all(
            hasattr(value, "steady_state_gain") for value in distributed.values()
        ):
            st_obj.markdown("**RDL 传递函数**")
            gains = best.steady_state_gains
            st_obj.dataframe(gains, width="stretch")
            coefficients = best.distributed_lag_coefficients
            st_obj.dataframe(coefficients, width="stretch")
            try:
                with matplotlib_date_compatibility():
                    figure, _ = best.plot_impulse_response()
                    render_pyplot_figure(st_obj, figure)
            except Exception as exc:  # noqa: BLE001 - 可选图表边界
                st_obj.warning(f"RDL 冲击权重图无法绘制：{exc}")
            return
        st_obj.markdown("**ARDL 滞后结构**")
        rows = [{"变量": "目标变量", "滞后": repr(getattr(best, "ar_lags", ()))}]
        rows.extend(
            {"变量": name, "滞后": repr(lags)}
            for name, lags in distributed.items()
        )
        st_obj.dataframe(pd.DataFrame(rows), width="stretch")
        st_obj.metric(
            "目标 AR 稳定性",
            "平稳" if getattr(best, "is_stationary", False) else "非平稳",
            delta_color="off",
        )
        return
    st_obj.markdown("**SARIMAX 根条件**")
    _render_root_conditions(st_obj, best)


__all__ = ["render_analysis_section"]
