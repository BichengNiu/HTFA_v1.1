"""SARIMAX 工作流 - ② 残差诊断环节。"""

from __future__ import annotations

import logging

from dashboard.core.ui.utils.chart_legend import render_pyplot_figure
from dashboard.core.ui.utils.matplotlib_compat import matplotlib_date_compatibility
from dashboard.core.workspace import stable_signature
from dashboard.models.common.workflow import ModelWorkflow
from dashboard.models.SARIMAX.core.adapters import DynamicRegressionAdapter
from dashboard.models.SARIMAX.ui.state import state

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
            state.set("diagnostics_table", None)
            state.set("diagnostics_signature", None)
            return
        state.set("diagnostics_table", table)
        state.set("diagnostics_signature", signature)

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
