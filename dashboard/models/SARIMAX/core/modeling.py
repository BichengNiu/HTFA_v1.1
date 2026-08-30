"""SARIMAX 拟合、诊断与预测编排（唯一调用 Ts 包的模块，无 streamlit 依赖）。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from Ts.TsModels import (
    ARDL,
    SARIMAX,
    AutoARDL,
    AutoARDLResult,
    AutoModelResult,
    AutoSARIMAX,
    RationalLagSpec,
    SARIMAXResult,
)
from Ts.TsPlots import plot_series
from Ts.TsSims import simulate_sarimax

from dashboard.models.SARIMAX.core.model_config import (
    AUTO_CRITERIA,
    ARDLConfig,
    AutoARDLConfig,
    AutoRDLConfig,
    AutoSARIMAXConfig,
    RDLConfig,
    SARIMAXConfig,
)

MIN_OBSERVATIONS = 10
ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True)
class SARIMAXSimulationComparison:
    """实际建模序列与一次理论模拟路径的对比数据。"""

    actual: np.ndarray
    theoretical: np.ndarray
    index: pd.Index
    seed: int

    def __post_init__(self) -> None:
        actual = np.asarray(self.actual, dtype=float)
        theoretical = np.asarray(self.theoretical, dtype=float)
        if actual.ndim != 1 or theoretical.ndim != 1:
            raise ValueError("实际序列和理论序列必须是一维数组")
        if len(actual) != len(theoretical):
            raise ValueError("实际序列和理论序列长度必须一致")
        index = pd.Index(self.index).copy()
        if len(index) != len(actual):
            raise ValueError("序列索引长度必须与序列长度一致")
        if not np.all(np.isfinite(actual)) or not np.all(np.isfinite(theoretical)):
            raise ValueError("实际序列和理论序列必须只包含有限值")
        if isinstance(self.seed, bool) or not isinstance(self.seed, (int, np.integer)):
            raise TypeError("seed 必须是整数")
        object.__setattr__(self, "actual", actual.copy())
        object.__setattr__(self, "theoretical", theoretical.copy())
        object.__setattr__(self, "index", index)
        object.__setattr__(self, "seed", int(self.seed))

    @property
    def rmse(self) -> float:
        """返回两条序列的均方根误差。"""
        return float(np.sqrt(np.mean(np.square(self.actual - self.theoretical))))

    @property
    def mae(self) -> float:
        """返回两条序列的平均绝对误差。"""
        return float(np.mean(np.abs(self.actual - self.theoretical)))


# Ts 包英文错误消息 → 用户可读中文提示的映射（按出现顺序匹配）。
_SARIMAX_ERROR_HINTS = (
    (
        "Need at least 10 observations",
        "样本量不足：SARIMAX 至少需要 10 个观测值",
    ),
    (
        "log transformation requires strictly positive data",
        "已启用 log 变换，但数据存在非正值",
    ),
    (
        "SARIMAX optimization failed to converge",
        "模型优化未收敛，请尝试更换优化器、增大最大迭代次数或简化阶数",
    ),
    (
        "future exog",
        "未来外生变量数据有误",
    ),
    (
        "exog",
        "外生变量数据有误",
    ),
    (
        "seasonal_order",
        "季节阶数设置有误",
    ),
    (
        "rank deficient",
        "外生变量设计与趋势项存在共线性或全零列",
    ),
)

_DIAGNOSTIC_ROWS = (
    ("white_noise", "残差自相关（Ljung-Box）"),
    ("normality", "残差正态性（Jarque-Bera）"),
    ("ljung_box", "ARCH 效应（平方残差 Ljung-Box）"),
    ("engle_lm", "ARCH 效应（Engle LM）"),
)


def translate_ts_error(error: Exception) -> str:
    """把 Ts 包抛出的异常转译为面向用户的中文消息。"""
    message = str(error).strip()
    for fragment, hint in _SARIMAX_ERROR_HINTS:
        if fragment in message:
            return f"{hint}：{message}"
    if message:
        return message
    return (
        f"{type(error).__name__}：异常未提供详细信息；"
        "请缩小自动选阶范围后重试，并检查运行日志。"
    )


DynamicConfig = (
    SARIMAXConfig
    | AutoSARIMAXConfig
    | RDLConfig
    | AutoRDLConfig
    | ARDLConfig
    | AutoARDLConfig
)


def _is_dynamic_regression(config: DynamicConfig) -> bool:
    return isinstance(config, (RDLConfig, AutoRDLConfig, ARDLConfig, AutoARDLConfig))


def validate_fit_inputs(
    series: pd.Series,
    exog: pd.DataFrame | None,
    config: DynamicConfig,
) -> list[str]:
    """拟合前预检，返回用户可读的问题列表；空列表表示可以拟合。"""
    problems: list[str] = []
    if series is None:
        problems.append("尚未选择目标变量")
        return problems

    valid = series.dropna()
    if len(valid) < MIN_OBSERVATIONS:
        problems.append(
            f"样本量不足：有效观测 {len(valid)} 个，模型至少需要 "
            f"{MIN_OBSERVATIONS} 个"
        )
    if config.log and len(valid) > 0 and float(valid.min()) <= 0.0:
        problems.append("已启用 log 变换，但目标序列存在非正值")

    if exog is not None:
        if not exog.index.equals(series.index):
            problems.append("外生变量与目标序列索引不一致，请重新选择外生变量")
        missing = int(exog.isna().sum().sum())
        if missing:
            problems.append(
                f"外生变量存在 {missing} 个缺失值，拟合时将按 missing='drop' "
                "丢弃对应行"
            )

    if _is_dynamic_regression(config):
        if exog is None or exog.shape[1] == 0:
            problems.append("RDL/ARDL 至少需要选择一个解释变量")
        if series.isna().any() or (exog is not None and exog.isna().any().any()):
            problems.append(
                "动态回归不接受缺失导致的非连续样本；请先补齐或删除不完整期"
            )

    seasonal_period = 0
    if isinstance(config, (SARIMAXConfig, RDLConfig)):
        seasonal_period = (
            config.seasonal_order[3]
            if isinstance(config, SARIMAXConfig)
            else config.error.seasonal_order[3]
        )
    elif isinstance(config, (AutoSARIMAXConfig, AutoRDLConfig)):
        seasonal_period = config.s if isinstance(config, AutoSARIMAXConfig) else config.error.s
    elif config.seasonal:
        seasonal_period = config.period or 0
    if seasonal_period > 0 and len(valid) < 2 * seasonal_period:
        problems.append(
            f"季节周期 s={seasonal_period} 过大：至少需要 {2 * seasonal_period} "
            "个观测才能估计季节项"
        )
    return problems


def fit_sarimax(
    series: pd.Series,
    exog: pd.DataFrame | None,
    config: SARIMAXConfig,
) -> SARIMAXResult:
    """按手动配置拟合 SARIMAX 模型并返回 Ts 结果对象。"""
    model = SARIMAX(
        series,
        order=config.order,
        seasonal_order=config.seasonal_order,
        trend=config.trend,
        exog=exog,
        log=config.log,
        enforce_stationarity=config.enforce_stationarity,
        enforce_invertibility=config.enforce_invertibility,
    )
    return model.fit(
        method=config.fit_method,
        maxiter=config.maxiter,
        cov_type=config.cov_type,
    )


def _fitted_coefficients(
    params: Any,
    prefix: str,
    count: int,
    *,
    seasonal_period: int | None = None,
) -> list[float]:
    """读取拟合结果中的连续 AR/MA 参数并校验数值。"""
    coefficients = []
    for lag in range(1, count + 1):
        name = (
            f"{prefix}.S.L{seasonal_period * lag}"
            if seasonal_period is not None
            else f"{prefix}.L{lag}"
        )
        try:
            value = float(params[name])
        except KeyError as exc:
            raise ValueError(f"拟合结果缺少参数 {name}") from exc
        if not np.isfinite(value):
            raise ValueError(f"拟合参数 {name} 不是有限值")
        coefficients.append(value)
    return coefficients


def build_sarimax_simulation_comparison(
    result: Any,
    *,
    seed: int = 42,
) -> SARIMAXSimulationComparison:
    """根据已估计的纯 SARIMAX 参数生成一条理论模拟路径。

    该函数把拟合结果中的趋势和静态外生变量贡献作为确定性路径，
    再交给 ``TsSims.simulate_sarimax`` 生成同长度的 SARIMA 随机误差。
    ``log=True`` 时，模拟过程在 log 尺度完成，最后还原到原始响应尺度。

    Parameters
    ----------
    result : SARIMAXResult
        已拟合的纯 SARIMAX 结果；自动选阶结果应先传入其最佳模型。
    seed : int, default=42
        理论模拟路径使用的随机种子；相同拟合结果和种子会产生相同路径。

    Returns
    -------
    SARIMAXSimulationComparison
        包含实际建模序列、理论模拟序列、共同索引和误差指标的对比对象。

    Raises
    ------
    ValueError
        结果不是纯 SARIMAX、参数不完整、序列长度不一致或模拟结果无效时。
    TypeError
        ``seed`` 不是整数时。
    """
    if getattr(result, "model_type", None) != "SARIMAX":
        raise ValueError("理论模拟图只支持纯 SARIMAX 模型")
    if getattr(result, "distributed_lag_names", ()):
        raise ValueError("理论模拟图不支持带传递函数的 RDL 模型")
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
        raise TypeError("seed 必须是整数")

    order = getattr(result, "order", None)
    seasonal_order = getattr(result, "seasonal_order", None)
    if order is None or seasonal_order is None:
        raise ValueError("拟合结果缺少 SARIMAX 阶数")
    order = tuple(int(value) for value in order)
    seasonal_order = tuple(int(value) for value in seasonal_order)
    if len(order) != 3 or len(seasonal_order) != 4:
        raise ValueError("拟合结果中的 SARIMAX 阶数格式无效")

    nobs = int(getattr(result, "nobs", 0))
    actual = np.asarray(getattr(result, "data", None), dtype=float)
    if nobs <= 0 or actual.ndim != 1 or len(actual) != nobs:
        raise ValueError("拟合结果的实际序列长度无效")
    if not np.all(np.isfinite(actual)):
        raise ValueError("拟合结果的实际序列包含非有限值")

    params = getattr(result, "params", None)
    if not hasattr(params, "__getitem__"):
        raise ValueError("拟合结果缺少参数映射")
    p, _d, q = order
    P, _D, Q, seasonal_period = seasonal_order
    ar = _fitted_coefficients(params, "ar", p)
    ma = _fitted_coefficients(params, "ma", q)
    seasonal_ar = _fitted_coefficients(
        params,
        "ar",
        P,
        seasonal_period=seasonal_period,
    )
    seasonal_ma = _fitted_coefficients(
        params,
        "ma",
        Q,
        seasonal_period=seasonal_period,
    )
    try:
        sigma2 = float(params["sigma2"])
    except KeyError as exc:
        raise ValueError("拟合结果缺少参数 sigma2") from exc
    if not np.isfinite(sigma2) or sigma2 <= 0.0:
        raise ValueError("拟合参数 sigma2 必须是正的有限值")

    deterministic = np.asarray(result.deterministic_component, dtype=float)
    if deterministic.ndim != 1 or len(deterministic) != nobs:
        raise ValueError("拟合结果的确定性响应路径长度无效")
    simulation = simulate_sarimax(
        n=nobs,
        order=order,
        seasonal_order=seasonal_order,
        ar=ar,
        ma=ma,
        seasonal_ar=seasonal_ar,
        seasonal_ma=seasonal_ma,
        deterministic=deterministic,
        sigma2=sigma2,
        seed=int(seed),
    )
    theoretical = np.asarray(simulation.data, dtype=float)
    if getattr(result, "log", False):
        with np.errstate(over="ignore", invalid="ignore"):
            theoretical = np.exp(theoretical)
    if theoretical.ndim != 1 or len(theoretical) != nobs:
        raise ValueError("理论模拟序列长度与实际建模序列不一致")
    if not np.all(np.isfinite(theoretical)):
        raise ValueError("理论模拟序列包含非有限值")

    dates = getattr(result, "dates", None)
    if dates is None:
        index = pd.RangeIndex(1, nobs + 1, name="期数")
    else:
        index = pd.DatetimeIndex(pd.to_datetime(dates))
        if len(index) != nobs or index.isna().any():
            raise ValueError("拟合结果的日期索引长度无效")
        index = index.rename("日期")
    return SARIMAXSimulationComparison(
        actual=actual,
        theoretical=theoretical,
        index=index,
        seed=int(seed),
    )


def plot_sarimax_simulation_comparison(
    comparison: SARIMAXSimulationComparison,
) -> tuple[Any, Any]:
    """用 TsPlots 绘制实际序列与理论模拟序列的叠加图。

    Parameters
    ----------
    comparison : SARIMAXSimulationComparison
        已生成的实际序列与理论模拟序列对比数据。

    Returns
    -------
    tuple
        ``(figure, axes)`` 形式的 TsPlots 图形对象。
    """
    frame = pd.DataFrame(
        {
            "实际序列": comparison.actual,
            "理论模拟序列": comparison.theoretical,
        },
        index=comparison.index,
    )
    return plot_series(
        frame,
        title="实际序列与理论模拟序列",
        xtitle="",
        ytitle="",
        linewidth=2.0,
        markersize=0,
        show_legend=True,
        facet=False,
        auto_dual_y=False,
        grid=False,
    )


def fit_auto_sarimax(
    series: pd.Series,
    exog: pd.DataFrame | None,
    config: AutoSARIMAXConfig,
    *,
    progress_callback: ProgressCallback | None = None,
) -> AutoModelResult:
    """按搜索范围自动选阶并返回 Ts 结果对象。

    Parameters
    ----------
    series : pandas.Series
        目标时间序列。
    exog : pandas.DataFrame or None
        可选的外生变量表。
    config : AutoSARIMAXConfig
        自动 SARIMAX 配置。
    progress_callback : callable, optional
        每完成一个候选模型后，在主进程中调用
        ``callback(completed, total)``。
    """
    model = AutoSARIMAX(
        series,
        p=config.p,
        d=config.d,
        q=config.q,
        P=config.P,
        D=config.D,
        Q=config.Q,
        s=config.s,
        trend=config.trend,
        criterion=config.criterion,
        exog=exog,
        log=config.log,
        fit_method=config.fit_method,
        maxiter=config.maxiter,
        cov_type=config.cov_type,
        enforce_stationarity=config.enforce_stationarity,
        enforce_invertibility=config.enforce_invertibility,
    )
    return model.fit(progress_callback=progress_callback)


def format_sarimax_order(
    order: tuple[int, int, int],
    seasonal_order: tuple[int, int, int, int] | None = None,
) -> str:
    """将 SARIMAX 阶数格式化为完整的 `(p,d,q)(P,D,Q,S)` 标签。

    Parameters
    ----------
    order : tuple[int, int, int]
        非季节阶数 `(p,d,q)`。
    seasonal_order : tuple[int, int, int, int] or None, optional
        季节阶数 `(P,D,Q,S)`；省略时使用无季节项 `(0,0,0,0)`。

    Returns
    -------
    str
        形如 ``SARIMAX(2, 0, 1)(1, 0, 1, 252)`` 的完整模型标签。
    """
    seasonal = (0, 0, 0, 0) if seasonal_order is None else tuple(seasonal_order)
    return f"SARIMAX{tuple(order)}{seasonal}"


def build_auto_sarimax_criterion_table(result: AutoModelResult) -> pd.DataFrame:
    """构建自动 SARIMAX 候选模型的多准则比较表。

    Parameters
    ----------
    result : AutoModelResult
        AutoSARIMAX 搜索结果，必须包含候选模型结果。

    Returns
    -------
    pandas.DataFrame
        行为候选模型，列为模型标签、AIC、BIC、HQIC 和 AICC。
        信息准则数值越小越优。
    """
    criterion_values = result.criterion_table
    rows = []
    for index, order in enumerate(result.candidate_orders):
        seasonal = (
            result.candidate_seasonal_orders[index]
            if index < len(result.candidate_seasonal_orders)
            else None
        )
        label = format_sarimax_order(order, seasonal)
        rows.append(
            {
                "模型": label,
                **{
                    criterion.upper(): round(
                        float(criterion_values.iloc[index][criterion]), 6
                    )
                    for criterion in AUTO_CRITERIA
                },
            }
        )
    return pd.DataFrame(rows, columns=["模型", *(c.upper() for c in AUTO_CRITERIA)])


def select_auto_sarimax_result(
    result: AutoModelResult,
    criterion: str,
) -> AutoModelResult:
    """按指定信息准则从已有候选结果中选择最终模型。

    并行搜索返回轻量候选摘要时，仅对新选中的阶数重新拟合一次完整
    SARIMAX；串行搜索仍直接复用已有候选结果。

    Parameters
    ----------
    result : AutoModelResult
        已完成网格搜索的 AutoSARIMAX 结果。
    criterion : str
        选择准则，必须是 ``AUTO_CRITERIA`` 中的一项。

    Returns
    -------
    AutoModelResult
        以指定准则最小候选模型为 ``best_result`` 的结果对象。
    """
    if criterion not in AUTO_CRITERIA:
        raise ValueError(f"criterion 必须是 {AUTO_CRITERIA} 之一")
    values = pd.to_numeric(
        result.criterion_table[criterion], errors="coerce"
    ).to_numpy(dtype=float)
    finite = np.isfinite(values)
    if not finite.any():
        raise ValueError(f"{criterion} 没有可用的候选值")
    best_index = int(np.where(finite, values, np.inf).argmin())
    seasonal = (
        result.candidate_seasonal_orders[best_index]
        if best_index < len(result.candidate_seasonal_orders)
        else None
    )
    best_result = result._refit_candidate(best_index)
    return AutoModelResult.from_search(
        best_result=best_result,
        best_order=result.candidate_orders[best_index],
        candidate_results=result.candidate_results,
        candidate_orders=result.candidate_orders,
        criterion_values=values.tolist(),
        selection_criterion=criterion,
        search_method=result.search_method,
        n_attempted=result.n_attempted,
        best_seasonal_order=seasonal,
        candidate_seasonal_orders=result.candidate_seasonal_orders,
        search_messages=result.search_messages,
        search_metadata=getattr(result, "search_metadata", None),
        candidate_model_kwargs=result._candidate_model_kwargs,
        candidate_fit_kwargs=result._candidate_fit_kwargs,
    )


def _rdl_specs(config: RDLConfig | AutoRDLConfig) -> dict[str, RationalLagSpec]:
    """将 UI 层传递函数配置转换为 Ts 的不可变规格。"""
    specs = {}
    for item in config.inputs:
        numerator, denominator, delay, initialization = item.specification()
        specs[item.name] = RationalLagSpec(
            numerator=numerator,
            denominator=denominator,
            delay=delay,
            initialization=initialization,
        )
    return specs


def fit_rdl(
    series: pd.Series,
    exog: pd.DataFrame,
    config: RDLConfig,
) -> SARIMAXResult:
    """拟合固定传递函数加 SARIMAX 误差的 RDL 模型。"""
    error = config.error
    model = SARIMAX(
        series,
        order=error.order,
        seasonal_order=error.seasonal_order,
        trend=error.trend,
        exog=exog,
        log=error.log,
        enforce_stationarity=error.enforce_stationarity,
        enforce_invertibility=error.enforce_invertibility,
        distributed_lags=_rdl_specs(config),
        enforce_distributed_lag_stability=config.enforce_distributed_lag_stability,
    )
    return model.fit(
        method=error.fit_method,
        maxiter=error.maxiter,
        cov_type=error.cov_type,
    )


def fit_auto_rdl(
    series: pd.Series,
    exog: pd.DataFrame,
    config: AutoRDLConfig,
    *,
    progress_callback: ProgressCallback | None = None,
) -> AutoModelResult:
    """仅自动搜索 RDL 的 SARIMAX 误差阶数，传递函数保持固定。

    Parameters
    ----------
    series : pandas.Series
        目标时间序列。
    exog : pandas.DataFrame
        外生变量表。
    config : AutoRDLConfig
        自动 RDL 配置。
    progress_callback : callable, optional
        每完成一个候选模型后，在主进程中调用
        ``callback(completed, total)``。
    """
    error = config.error
    model = AutoSARIMAX(
        series,
        p=error.p,
        d=error.d,
        q=error.q,
        P=error.P,
        D=error.D,
        Q=error.Q,
        s=error.s,
        trend=error.trend,
        criterion=error.criterion,
        exog=exog,
        log=error.log,
        fit_method=error.fit_method,
        maxiter=error.maxiter,
        cov_type=error.cov_type,
        enforce_stationarity=error.enforce_stationarity,
        enforce_invertibility=error.enforce_invertibility,
        distributed_lags=_rdl_specs(config),
        enforce_distributed_lag_stability=config.enforce_distributed_lag_stability,
    )
    return model.fit(progress_callback=progress_callback)


def fit_ardl(
    series: pd.Series,
    exog: pd.DataFrame,
    config: ARDLConfig,
):
    """拟合标准 ARDL，而非把 SARIMAX AR 误差误称为 ARDL。"""
    model = ARDL(
        series,
        lags=config.lags,
        exog=exog,
        order=config.order_mapping(),
        trend=config.trend,
        causal=config.causal,
        seasonal=config.seasonal,
        period=config.period,
        hold_back=config.hold_back,
        log=config.log,
    )
    return model.fit(cov_type=config.cov_type)


def fit_auto_ardl(
    series: pd.Series,
    exog: pd.DataFrame,
    config: AutoARDLConfig,
    *,
    progress_callback: ProgressCallback | None = None,
) -> AutoARDLResult:
    """按 AIC/BIC 自动选择标准 ARDL 的目标和逐输入滞后。

    Parameters
    ----------
    series : pandas.Series
        目标时间序列。
    exog : pandas.DataFrame
        外生变量表。
    config : AutoARDLConfig
        自动 ARDL 配置。
    progress_callback : callable, optional
        每完成一个候选模型后，在主进程中调用
        ``callback(completed, total)``。
    """
    model = AutoARDL(
        series,
        maxlag=config.maxlag,
        exog=exog,
        maxorder=config.maxorder_mapping(),
        trend=config.trend,
        criterion=config.criterion,
        search_method=config.search_method,
        causal=config.causal,
        seasonal=config.seasonal,
        period=config.period,
        hold_back=config.hold_back,
        log=config.log,
    )
    return model.fit(
        cov_type=config.cov_type,
        progress_callback=progress_callback,
    )


def fit_dynamic_model(
    series: pd.Series,
    exog: pd.DataFrame | None,
    config: DynamicConfig,
    *,
    progress_callback: ProgressCallback | None = None,
):
    """按模型族和配置方式分发到 Ts 的唯一拟合入口。

    Parameters
    ----------
    series : pandas.Series
        目标时间序列。
    exog : pandas.DataFrame or None
        可选的外生变量表；RDL/ARDL 必须提供。
    config : DynamicConfig
        SARIMAX、RDL 或 ARDL 配置对象。
    progress_callback : callable, optional
        自动选阶时，每完成一个候选模型后在主进程中调用
        ``callback(completed, total)``；手动模式忽略该回调。
    """
    if isinstance(config, SARIMAXConfig):
        return fit_sarimax(series, exog, config)
    if isinstance(config, AutoSARIMAXConfig):
        return fit_auto_sarimax(
            series,
            exog,
            config,
            progress_callback=progress_callback,
        )
    if exog is None:
        raise ValueError("RDL/ARDL 需要解释变量")
    if isinstance(config, RDLConfig):
        return fit_rdl(series, exog, config)
    if isinstance(config, AutoRDLConfig):
        return fit_auto_rdl(
            series,
            exog,
            config,
            progress_callback=progress_callback,
        )
    if isinstance(config, ARDLConfig):
        return fit_ardl(series, exog, config)
    if isinstance(config, AutoARDLConfig):
        return fit_auto_ardl(
            series,
            exog,
            config,
            progress_callback=progress_callback,
        )
    raise TypeError(f"不支持的动态回归配置：{type(config)!r}")


def run_residual_diagnostics(
    result: Any,
    lags: int = 10,
) -> pd.DataFrame:
    """对拟合结果执行残差诊断，返回结构化结果表。"""
    tests = result.test_residuals(lags=lags)
    rows = []
    for attribute, label in _DIAGNOSTIC_ROWS:
        item = getattr(tests, attribute)
        pvalue = float(item.pvalue)
        rows.append(
            {
                "检验": label,
                "统计量": float(item.statistic),
                "P值": pvalue,
                "结论": "拒绝原假设" if pvalue < 0.05 else "不拒绝原假设",
            }
        )
    return pd.DataFrame(rows, columns=["检验", "统计量", "P值", "结论"])


def recommended_residual_diagnostic_lags(nobs: int) -> int:
    """按有效残差数给出残差检验的建议最大滞后阶数。

    与 Ts 诊断图一致，使用 ``min(10, floor(n / 5))``；最小值为 1。
    该上限也为 Engle LM 辅助回归保留足够有效样本。
    """
    if nobs < 4:
        raise ValueError("有效残差至少需要 4 个才能执行残差诊断")
    return min(10, max(1, nobs // 5))


def future_dates(
    result: Any,
    steps: int,
    fallback_dates: pd.DatetimeIndex | None = None,
) -> pd.DatetimeIndex | None:
    """基于拟合日期频率推算未来预测日期；无法推断时返回 None。

    ``fallback_dates`` 用于拟合数据因缺失值而变得不连续时，
    从原始数据的完整日期列补充推断频率。
    """
    dates = result.dates
    if dates is None or len(dates) == 0:
        return None
    freq = dates.freq
    if freq is None:
        freq = pd.infer_freq(dates)
    if freq is None and fallback_dates is not None:
        fallback = pd.DatetimeIndex(fallback_dates)
        freq = fallback.freq or pd.infer_freq(fallback)
    if freq is None:
        return None
    offset = pd.tseries.frequencies.to_offset(freq)
    return pd.date_range(
        start=dates[-1] + offset,
        periods=steps,
        freq=offset,
    )


def produce_forecast(
    result: Any,
    start: int | str | pd.Timestamp,
    end: int | str | pd.Timestamp,
    alpha: float = 0.05,
    dynamic: bool = False,
    future_exog: pd.DataFrame | None = None,
    future_dates: pd.DatetimeIndex | None = None,
) -> dict[str, Any]:
    """对拟合结果预测，返回均值/区间/日期结构。

    Parameters
    ----------
    result : SARIMAXResult or compatible result
        已拟合的 Ts 模型结果。
    start : int or datetime-like
        预测起点；遵循 Ts ``predict`` 的位置/日期语义。
    end : int or datetime-like
        预测终点，包含该位置。
    alpha : float, default=0.05
        预测区间显著性水平。
    dynamic : bool, default=False
        传递给 Ts ``predict`` 的动态预测控制。
    future_exog : pandas.DataFrame or None, optional
        从拟合样本末期到 ``end`` 的完整未来外生变量路径。
    future_dates : pandas.DatetimeIndex or None, optional
        日期频率无法从拟合样本推断时使用的完整未来日期路径；直接传给 Ts。

    Returns
    -------
    dict
        包含 ``mean``、``lower``、``upper``、``dates``、``steps``、``start``、
        ``end``、``alpha`` 和 Ts 原始 ``prediction`` 对象的预测结构。
    """
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha 必须在 (0, 1) 区间内")

    predict_kwargs = {
        "start": start,
        "end": end,
        "dynamic": dynamic,
        "alpha": alpha,
        "future_exog": future_exog,
    }
    if future_dates is not None:
        predict_kwargs["future_dates"] = future_dates
    prediction = result.predict(
        **predict_kwargs,
    )
    mean = np.asarray(prediction.mean, dtype=float)
    lower = np.asarray(prediction.lower, dtype=float)
    upper = np.asarray(prediction.upper, dtype=float)
    steps = len(mean)
    return {
        "mean": mean,
        "lower": lower,
        "upper": upper,
        "prediction": prediction,
        "future_dates": (
            None
            if future_dates is None
            else pd.DatetimeIndex(future_dates).copy()
        ),
        "dates": _prediction_dates(
            result,
            start,
            end,
            steps,
            supplied_future_dates=future_dates,
        ),
        "steps": steps,
        "start": start,
        "end": end,
        "alpha": alpha,
    }


def _prediction_dates(
    result: Any,
    start: int | str | pd.Timestamp | None,
    end: int | str | pd.Timestamp | None,
    length: int,
    supplied_future_dates: pd.DatetimeIndex | None = None,
) -> pd.DatetimeIndex | None:
    """按 Ts 预测窗口位置还原结果日期。"""
    dates = result.dates
    if dates is None:
        return None
    dates = pd.DatetimeIndex(dates)
    if isinstance(start, (int, np.integer)) and (
        end is None or isinstance(end, (int, np.integer))
    ):
        start_pos = int(start)
        end_pos = start_pos + length - 1 if end is None else int(end)
        if end_pos < len(dates):
            return dates[start_pos : end_pos + 1]
        future = (
            pd.DatetimeIndex(supplied_future_dates)
            if supplied_future_dates is not None
            else future_dates(result, end_pos - len(dates) + 1)
        )
        if future is None:
            return None
        calendar = dates.append(future)
        return calendar[start_pos : end_pos + 1]

    if supplied_future_dates is not None:
        calendar = dates.append(pd.DatetimeIndex(supplied_future_dates))
        start_date = dates[0] if start is None else pd.Timestamp(start)
        end_date = dates[-1] if end is None else pd.Timestamp(end)
        selection = calendar[(calendar >= start_date) & (calendar <= end_date)]
        return pd.DatetimeIndex(selection[:length])

    frequency = dates.freq or pd.infer_freq(dates)
    if frequency is None:
        return None
    offset = pd.tseries.frequencies.to_offset(frequency)
    start_date = dates[0] if start is None else pd.Timestamp(start)
    end_date = (
        start_date + (length - 1) * offset
        if end is None
        else pd.Timestamp(end)
    )
    calendar = pd.date_range(
        start=dates[0],
        end=max(end_date, dates[-1]),
        freq=offset,
    )
    selection = calendar[(calendar >= start_date) & (calendar <= end_date)]
    return pd.DatetimeIndex(selection[:length])


def build_prediction_table(forecast: dict[str, Any]) -> pd.DataFrame:
    """把预测结构转换为可展示、可下载的表格。"""
    mean = np.asarray(forecast["mean"], dtype=float)
    lower = np.asarray(forecast["lower"], dtype=float)
    upper = np.asarray(forecast["upper"], dtype=float)
    dates = forecast.get("dates")
    if dates is not None:
        index = pd.DatetimeIndex(dates)
        index.name = "日期"
    else:
        start = forecast.get("start", 0)
        start = int(start) if isinstance(start, (int, np.integer)) else 0
        index = pd.RangeIndex(
            start + 1,
            start + len(mean) + 1,
            name="期数",
        )
    return pd.DataFrame(
        {
            "预测值": mean,
            "下界": lower,
            "上界": upper,
        },
        index=index,
    )


__all__ = [
    "MIN_OBSERVATIONS",
    "DynamicConfig",
    "SARIMAXSimulationComparison",
    "build_auto_sarimax_criterion_table",
    "build_prediction_table",
    "build_sarimax_simulation_comparison",
    "fit_ardl",
    "fit_auto_ardl",
    "fit_auto_rdl",
    "fit_auto_sarimax",
    "fit_dynamic_model",
    "fit_rdl",
    "fit_sarimax",
    "format_sarimax_order",
    "future_dates",
    "plot_sarimax_simulation_comparison",
    "produce_forecast",
    "run_residual_diagnostics",
    "select_auto_sarimax_result",
    "translate_ts_error",
    "validate_fit_inputs",
]
