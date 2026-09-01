"""SARIMAX 工作流 - ② 残差诊断环节。"""

from __future__ import annotations

import logging

from dashboard.core.ui.utils.chart_legend import render_pyplot_figure
from dashboard.core.ui.utils.matplotlib_compat import matplotlib_date_compatibility
from dashboard.core.workspace import stable_signature
from dashboard.models.common.workflow import ModelWorkflow
from dashboard.models.SARIMAX.core.adapters import DynamicRegressionAdapter
from dashboard.models.SARIMAX.ui.state import (
    clear_downstream_result,
    state,
    store_downstream_result,
)

logger = logging.getLogger(__name__)
_MODEL_WORKFLOW = ModelWorkflow(DynamicRegressionAdapter())


def render_analysis_section(st_obj) -> None:
    """展示已拟合模型的残差诊断图与残差检验。"""
    result = state.get("fitted_result")
    if result is None:
        st_obj.info("完成模型训练后可查看残差诊断结果。")
        return
    st_obj.markdown("**残差诊断图**")
    with matplotlib_date_compatibility():
        diagnostic_view = _MODEL_WORKFLOW.residual_diagnostics(result)
        if diagnostic_view.figure is not None:
            try:
                render_pyplot_figure(st_obj, diagnostic_view.figure)
            except Exception as exc:
                st_obj.warning(f"残差诊断图无法绘制：{exc}")
                logger.warning("动态回归诊断图绘制失败", exc_info=True)
    if diagnostic_view.figure_error:
        st_obj.warning(f"残差诊断图无法绘制：{diagnostic_view.figure_error}")
        logger.warning("动态回归诊断图绘制失败：%s", diagnostic_view.figure_error)
    _render_residual_tests(st_obj, result, diagnostic_view)
    _render_model_diagnostics(st_obj, result)


def _render_model_diagnostics(st_obj, result) -> None:
    """展示 ARMA 创新响应、RDL 输入响应和 AR/MA 根诊断。"""
    model_result = getattr(result, "best_result", result)
    ar_roots = tuple(getattr(model_result, "arroots", ()))
    ma_roots = tuple(getattr(model_result, "maroots", ()))
    if ar_roots or ma_roots:
        st_obj.markdown("**ARMA 创新脉冲响应**")
        steps = st_obj.number_input(
            "创新响应期数",
            min_value=1,
            max_value=200,
            value=20,
            step=1,
            key="sarimax_innovation_irf_steps",
        )
        try:
            with matplotlib_date_compatibility():
                figure = _plot_figure(
                    model_result.plot_innovation_impulse_response(
                        steps=int(steps)
                    )
                )
                render_pyplot_figure(st_obj, figure)
        except Exception as exc:
            st_obj.warning(f"ARMA 创新脉冲响应无法绘制：{exc}")
            logger.warning("ARMA 创新脉冲响应绘制失败", exc_info=True)
    if getattr(model_result, "distributed_lag_names", ()):
        st_obj.markdown("**RDL 输入冲击响应**")
        try:
            with matplotlib_date_compatibility():
                render_pyplot_figure(
                    st_obj,
                    _plot_figure(model_result.plot_impulse_response()),
                )
        except Exception as exc:
            st_obj.warning(f"RDL 输入冲击响应无法绘制：{exc}")
            logger.warning("RDL 输入冲击响应绘制失败", exc_info=True)
    if not (ar_roots or ma_roots):
        return
    st_obj.markdown("**Roots 稳定性**")
    try:
        roots = model_result.root_diagnostics
        ar_status = "平稳" if model_result.is_stationary else "不平稳"
        ma_status = "可逆" if model_result.is_invertible else "不可逆"
        st_obj.caption(f"AR：{ar_status}；MA：{ma_status}。根的模大于 1 表示位于单位圆外。")
        st_obj.dataframe(
            roots.rename(
                columns={
                    "component": "组成",
                    "root_real": "实部",
                    "root_imag": "虚部",
                    "modulus": "根模",
                    "inverse_modulus": "逆根模",
                    "outside_unit_circle": "单位圆外",
                }
            ),
            width="stretch",
        )
        with matplotlib_date_compatibility():
            render_pyplot_figure(st_obj, _plot_figure(model_result.plot_roots()))
    except Exception as exc:
        st_obj.warning(f"Roots 稳定性无法计算：{exc}")
        logger.warning("SARIMAX Roots 诊断失败", exc_info=True)


def _plot_figure(plot_result):
    """兼容 Ts 绘图 API 返回 Figure 或 ``(Figure, Axes)`` 的形式。"""
    if isinstance(plot_result, tuple):
        return plot_result[0]
    return plot_result


def _render_residual_tests(st_obj, result, diagnostic_view) -> None:
    """按建议滞后阶数自动运行并展示残差诊断检验。"""
    st_obj.markdown("**残差诊断检验**")
    st_obj.caption(
        f"有效残差 {diagnostic_view.effective_nobs} 个，系统按建议值 "
        f"{diagnostic_view.lags} 阶自动执行检验"
        "（min(10, floor(n / 5))）。"
    )
    signature = stable_signature(
        {
            "fit_signature": state.get("fit_signature"),
            "lags": diagnostic_view.lags,
        }
    )
    table = state.get("diagnostics_table")
    if table is None or state.get("diagnostics_signature") != signature:
        try:
            with st_obj.spinner("正在执行残差检验..."):
                table = _MODEL_WORKFLOW.residual_test_table(
                    result,
                    lags=diagnostic_view.lags,
                )
        except Exception as exc:
            st_obj.error(f"残差检验无法执行：{exc}")
            logger.exception("SARIMAX 残差检验失败")
            clear_downstream_result(
                "diagnostics_table",
                "diagnostics_signature",
            )
            return
        store_downstream_result(
            "diagnostics_table",
            table,
            "diagnostics_signature",
            signature,
        )

    st_obj.dataframe(
        table,
        width="stretch",
        column_config={
            "统计量": st_obj.column_config.NumberColumn(format="%.3f"),
            "P值": st_obj.column_config.NumberColumn(format="%.3f"),
        },
    )
    st_obj.download_button(
        "下载检验结果",
        data=table.to_csv(
            index=False,
            encoding="utf-8-sig",
            float_format="%.3f",
        ).encode("utf-8-sig"),
        file_name="SARIMAX_残差检验.csv",
        mime="text/csv",
        key="sarimax_diag_download",
        type="primary",
    )


__all__ = ["render_analysis_section"]
