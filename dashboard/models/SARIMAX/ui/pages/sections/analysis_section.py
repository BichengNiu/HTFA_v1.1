"""SARIMAX 工作流 - ② 残差诊断环节。"""

from __future__ import annotations

import logging

import pandas as pd

from dashboard.core.ui.utils.chart_legend import render_pyplot_figure
from dashboard.core.ui.utils.matplotlib_compat import matplotlib_date_compatibility
from dashboard.core.workspace import stable_signature
from dashboard.models.common.workflow import ModelWorkflow
from dashboard.models.SARIMAX.core.adapters import DynamicRegressionAdapter
from dashboard.models.SARIMAX.core.modeling import build_rdl_intervention_analysis
from dashboard.models.SARIMAX.core.rdl_config import RDL_INTERVENTION_NAME
from dashboard.models.SARIMAX.ui.state import ModelPageScope, SARIMAX_SCOPE

logger = logging.getLogger(__name__)
_MODEL_WORKFLOW = ModelWorkflow(DynamicRegressionAdapter())


def render_analysis_section(st_obj, scope: ModelPageScope = SARIMAX_SCOPE) -> None:
    """展示已拟合模型的残差诊断图与残差检验。"""
    state = scope.state
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
    _render_residual_tests(st_obj, result, diagnostic_view, scope)
    _render_model_diagnostics(st_obj, result, scope)


def _render_model_diagnostics(st_obj, result, scope: ModelPageScope) -> None:
    """展示 ARMA 创新响应、RDL 输入响应和 AR/MA 根诊断。"""
    model_result = getattr(result, "best_result", result)
    ar_roots = tuple(getattr(model_result, "arroots", ()))
    ma_roots = tuple(getattr(model_result, "maroots", ()))
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
        if scope.family == "RDL":
            _render_rdl_intervention_analysis(st_obj, model_result, scope)
    if not (ar_roots or ma_roots):
        return

    try:
        roots = model_result.root_diagnostics
        ar_status = "平稳" if model_result.is_stationary else "不平稳"
        ma_status = "可逆" if model_result.is_invertible else "不可逆"
        st_obj.markdown("**Roots 稳定性表**")
        st_obj.caption(
            f"AR：{ar_status}；MA：{ma_status}。根的模大于 1 表示位于单位圆外。"
        )
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
    except Exception as exc:
        st_obj.warning(f"Roots 稳定性无法计算：{exc}")
        logger.warning("SARIMAX Roots 诊断失败", exc_info=True)
    _render_cycle_diagnostics(st_obj, model_result)

    chart_columns = st_obj.columns(2)
    _render_innovation_impulse_response(
        chart_columns[0],
        model_result,
        session_state=st_obj.session_state,
        key=scope.key("innovation_irf_steps"),
    )
    _render_roots_plot(chart_columns[1], model_result)


def _plot_figure(plot_result):
    """兼容 Ts 绘图 API 返回 Figure 或 ``(Figure, Axes)`` 的形式。"""
    if isinstance(plot_result, tuple):
        return plot_result[0]
    return plot_result


def _render_innovation_impulse_response(
    st_obj,
    model_result,
    *,
    session_state,
    key: str,
) -> None:
    """在布局列中展示 ARMA 创新脉冲响应图。"""
    st_obj.markdown("**ARMA 创新脉冲响应图**")
    if key not in session_state:
        session_state[key] = 20
    steps = st_obj.number_input(
        "创新响应期数",
        min_value=1,
        max_value=200,
        step=1,
        key=key,
    )
    try:
        with matplotlib_date_compatibility():
            figure = _plot_figure(
                model_result.plot_innovation_impulse_response(steps=int(steps))
            )
            render_pyplot_figure(st_obj, figure)
    except Exception as exc:
        st_obj.warning(f"ARMA 创新脉冲响应无法绘制：{exc}")
        logger.warning("ARMA 创新脉冲响应绘制失败", exc_info=True)


def _render_roots_plot(st_obj, model_result) -> None:
    """在布局列中展示 Roots 稳定性图。"""
    st_obj.markdown("**Roots 稳定性图**")
    try:
        with matplotlib_date_compatibility():
            render_pyplot_figure(st_obj, _plot_figure(model_result.plot_roots()))
    except Exception as exc:
        st_obj.warning(f"Roots 稳定性图无法绘制：{exc}")
        logger.warning("SARIMAX Roots 稳定性图绘制失败", exc_info=True)


def _render_rdl_intervention_analysis(st_obj, model_result, scope) -> None:
    """展示日期干预路径与 RDL 事实/反事实结果。"""
    intervention = scope.state.get("intervention_config")
    if intervention is None:
        return
    st_obj.markdown("**RDL 干预分析**")
    try:
        analysis = build_rdl_intervention_analysis(model_result, intervention)
        input_result = model_result.distributed_lags[RDL_INTERVENTION_NAME]
        st_obj.caption(
            "I 是 0/1 干预路径；动态响应由 I 的 RDL 传递函数估计，"
            "不代表自动因果效应。"
        )
        st_obj.dataframe(
            analysis.table(),
            width="stretch",
            key=scope.key("intervention_result"),
        )
        spec = input_result.spec
        transfer_frame = pd.DataFrame(
            [
                {
                    "输入": "I（干预变量）",
                    "分子主动滞后": ", ".join(
                        str(lag) for lag in spec.numerator_lags
                    ),
                    "分母主动滞后": ", ".join(
                        str(lag) for lag in spec.denominator_lags
                    ) or "无",
                    "延迟": spec.delay,
                    "初始化": spec.initialization,
                }
            ]
        )
        st_obj.caption("I 的 RDL 传递函数设置")
        st_obj.dataframe(transfer_frame, width="stretch")
        gain = input_result.gain()
        gain_frame = pd.DataFrame([gain]).rename(
            columns={
                "input": "输入",
                "estimate": "稳态增益",
                "standard_error": "标准误",
                "lower": "下界",
                "upper": "上界",
                "stable": "稳定",
            }
        )
        st_obj.dataframe(gain_frame, width="stretch")
        weights = input_result.weights(20).rename("I 动态权重").to_frame()
        st_obj.caption("I 的 RDL 动态权重（前 20 期）")
        st_obj.dataframe(weights, width="stretch")
        if analysis.log_scale:
            st_obj.caption(
                "当前为 log(Y) 模型：相对变化（%）= 100 × "
                "(exp(模型尺度响应) − 1)。"
            )
        st_obj.line_chart(
            analysis.table()[["有干预 Y", "无干预 Y"]],
            width="stretch",
        )
        st_obj.line_chart(
            analysis.table()[["干预差异"]],
            width="stretch",
        )
    except Exception as exc:  # noqa: BLE001 - 用户可读的分析边界
        st_obj.warning(f"RDL 干预分析无法生成：{exc}")
        logger.warning("RDL 干预分析失败", exc_info=True)


def _cycle_diagnostics(model_result) -> tuple:
    """收集 Ts 提供的可用 AR(2) 周期诊断。"""
    cycle_period = getattr(model_result, "cycle_period", None)
    if not callable(cycle_period):
        return ()

    diagnostics = []
    for seasonal in (False, True):
        try:
            diagnostics.append(cycle_period(seasonal=seasonal))
        except ValueError:
            # Ts 以 ValueError 表示该模型没有对应的连续 AR(1, 2) 分量。
            continue
        except (RuntimeError, TypeError) as exc:
            logger.warning(
                "SARIMAX %s AR(2) 周期诊断失败：%s",
                "季节" if seasonal else "非季节",
                exc,
            )
    return tuple(diagnostics)


def _cycle_conclusion(diagnostic) -> str:
    """将 Ts ARCycleResult 的条件诊断转换为页面文案。"""
    if diagnostic.period is not None:
        return "已识别阻尼周期"
    if not diagnostic.has_complex_roots:
        return "实根：不构成振荡周期"
    if not diagnostic.is_stationary:
        return "复根，但 AR 不平稳"
    return "复根，但未形成有效周期"


def _render_cycle_diagnostics(st_obj, model_result) -> None:
    """展示 Ts AR(2) 复根周期识别结果。"""
    diagnostics = _cycle_diagnostics(model_result)
    if not diagnostics:
        return

    st_obj.markdown("**AR(2) 周期识别**")
    st_obj.caption(
        "周期由 AR(2) 复根的角频率计算；季节 AR(2) 已按季节周期 s 换算为原始观测期数。"
    )
    rows = []
    for diagnostic in diagnostics:
        component = (
            "季节 AR(2)"
            if diagnostic.component == "seasonal"
            else "非季节 AR(2)"
        )
        if diagnostic.component == "seasonal":
            component += f"（s={diagnostic.lag_scale}）"
        rows.append(
            {
                "组成": component,
                "φ₁": diagnostic.phi1,
                "φ₂": diagnostic.phi2,
                "判别式 Δ": diagnostic.discriminant,
                "复根": "是" if diagnostic.has_complex_roots else "否",
                "AR 平稳": "是" if diagnostic.is_stationary else "否",
                "周期（观测期）": diagnostic.period,
                "结论": _cycle_conclusion(diagnostic),
            }
        )
    st_obj.dataframe(
        pd.DataFrame(rows),
        width="stretch",
        column_config={
            "φ₁": st_obj.column_config.NumberColumn(format="%.4f"),
            "φ₂": st_obj.column_config.NumberColumn(format="%.4f"),
            "判别式 Δ": st_obj.column_config.NumberColumn(format="%.4f"),
            "周期（观测期）": st_obj.column_config.NumberColumn(format="%.2f"),
        },
    )


def _render_residual_tests(st_obj, result, diagnostic_view, scope: ModelPageScope) -> None:
    """按建议滞后阶数自动运行并展示残差诊断检验。"""
    st_obj.markdown("**残差诊断检验**")
    st_obj.caption(
        f"有效残差 {diagnostic_view.effective_nobs} 个，系统按建议值 "
        f"{diagnostic_view.lags} 阶自动执行检验"
        "（min(10, floor(n / 5))）。"
    )
    signature = stable_signature(
        {
            "fit_signature": scope.state.get("fit_signature"),
            "lags": diagnostic_view.lags,
        }
    )
    table = scope.state.get("diagnostics_table")
    if table is None or scope.state.get("diagnostics_signature") != signature:
        try:
            with st_obj.spinner("正在执行残差检验..."):
                table = _MODEL_WORKFLOW.residual_test_table(
                    result,
                    lags=diagnostic_view.lags,
                )
        except Exception as exc:
            st_obj.error(f"残差检验无法执行：{exc}")
            logger.exception("SARIMAX 残差检验失败")
            scope.clear_downstream_result(
                "diagnostics_table",
                "diagnostics_signature",
            )
            return
        scope.store_downstream_result(
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
        file_name=f"{scope.family}_残差检验.csv",
        mime="text/csv",
        key=scope.key("diag_download"),
        type="primary",
    )


__all__ = ["render_analysis_section"]
