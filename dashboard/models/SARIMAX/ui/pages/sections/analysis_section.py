"""SARIMAX 工作流 - ③ 残差诊断环节。"""

from __future__ import annotations

import logging

from Ts.TsModels import AutoARDLResult, AutoModelResult

from dashboard.core.ui.utils.chart_legend import render_pyplot_figure
from dashboard.core.ui.utils.matplotlib_compat import matplotlib_date_compatibility
from dashboard.core.workspace import stable_signature
from dashboard.models.SARIMAX.core.modeling import run_residual_diagnostics
from dashboard.models.SARIMAX.ui.state import state

logger = logging.getLogger(__name__)

_DEFAULT_LAGS = 10


def render_analysis_section(st_obj) -> None:
    """展示已拟合模型的残差诊断图与残差检验。"""
    st_obj.markdown("#### ③ 残差诊断")
    result = state.get("fitted_result")
    if result is None:
        st_obj.info("完成「② 模型训练」后可查看残差诊断结果。")
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
    signature = stable_signature(
        {"fit_signature": state.get("fit_signature"), "lags": int(lags)}
    )
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


__all__ = ["render_analysis_section"]
