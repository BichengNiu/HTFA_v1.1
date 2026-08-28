"""SARIMAX 工作流 - ② 残差诊断环节。"""

from __future__ import annotations

import logging

import numpy as np
from Ts.TsModels import AutoARDLResult, AutoModelResult

from dashboard.core.ui.utils.chart_legend import render_pyplot_figure
from dashboard.core.ui.utils.matplotlib_compat import matplotlib_date_compatibility
from dashboard.core.workspace import stable_signature
from dashboard.models.SARIMAX.core.modeling import (
    recommended_residual_diagnostic_lags,
    run_residual_diagnostics,
)
from dashboard.models.SARIMAX.ui.state import state

logger = logging.getLogger(__name__)

def render_analysis_section(st_obj) -> None:
    """展示已拟合模型的残差诊断图与残差检验。"""
    st_obj.markdown("#### ② 残差诊断")
    result = state.get("fitted_result")
    if result is None:
        st_obj.info("完成「① 模型训练」后可查看残差诊断结果。")
        return
    best = (
        result.best_result
        if isinstance(result, (AutoModelResult, AutoARDLResult))
        else result
    )
    st_obj.markdown("**残差诊断图**")
    try:
        with matplotlib_date_compatibility():
            figure, _ = best.plot_diagnostics()
            render_pyplot_figure(st_obj, figure)
    except Exception as exc:
        st_obj.warning(f"残差诊断图无法绘制：{exc}")
        logger.warning("动态回归诊断图绘制失败", exc_info=True)
    _render_residual_tests(st_obj, best)


def _render_residual_tests(st_obj, best) -> None:
    """按建议滞后阶数自动运行并展示残差诊断检验。"""
    st_obj.markdown("**残差诊断检验**")
    residuals = np.asarray(best.residuals, dtype=float)
    nobs = int(np.isfinite(residuals).sum())
    lags = recommended_residual_diagnostic_lags(nobs)
    st_obj.caption(
        f"有效残差 {nobs} 个，系统按建议值 {lags} 阶自动执行检验"
        "（min(10, floor(n / 5))）。"
    )
    signature = stable_signature(
        {"fit_signature": state.get("fit_signature"), "lags": lags}
    )
    table = state.get("diagnostics_table")
    if table is None or state.get("diagnostics_signature") != signature:
        try:
            with st_obj.spinner("正在调用 Ts 包执行残差检验..."):
                table = run_residual_diagnostics(best, lags=lags)
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
