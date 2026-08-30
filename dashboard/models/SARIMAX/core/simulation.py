"""SARIMAX 参数模拟与路径分布比较（纯计算，不依赖 Streamlit）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from Ts.TsSims import simulate_sarimax


def _sample_acf(values: np.ndarray, nlags: int) -> np.ndarray:
    """计算样本 ACF，返回滞后 1 至 ``nlags`` 的结果。"""
    from statsmodels.tsa.stattools import acf

    values = np.asarray(values, dtype=float)
    if np.isclose(np.var(values), 0.0):
        raise ValueError("ACF 无法用于方差为零的序列")
    result = np.asarray(acf(values, nlags=nlags, fft=True), dtype=float)[1:]
    if result.shape != (nlags,) or not np.all(np.isfinite(result)):
        raise ValueError("ACF 计算结果包含非有限值")
    return result


def _central_interval(values: np.ndarray, confidence_level: float) -> tuple[float, float]:
    """返回数组的中心模拟区间。"""
    tail = (1.0 - confidence_level) / 2.0
    quantiles = np.quantile(values, (tail, 1.0 - tail))
    return float(quantiles[0]), float(quantiles[1])


def _value_in_interval(value: float, interval: tuple[float, float]) -> bool:
    """判断一个值是否位于闭区间内。"""
    return bool(interval[0] <= value <= interval[1])


def _count_turning_points(values: np.ndarray) -> int:
    """统计严格局部极大值和极小值，不把平台段算作转折点。"""
    differences = np.diff(np.asarray(values, dtype=float))
    return int(np.count_nonzero(differences[:-1] * differences[1:] < 0.0))


@dataclass(frozen=True)
class SARIMAXSimulationComparison:
    """实际建模序列与多条参数模拟路径及其统计比较。"""

    actual: np.ndarray
    simulated: np.ndarray
    index: pd.Index
    seed: int
    confidence_level: float = 0.95
    acf_lags: int = 10
    _actual_acf: np.ndarray = field(init=False, repr=False)
    _simulated_acf: np.ndarray = field(init=False, repr=False)

    def __post_init__(self) -> None:
        actual = np.asarray(self.actual, dtype=float)
        simulated = np.asarray(self.simulated, dtype=float)
        if actual.ndim != 1 or simulated.ndim != 2:
            raise ValueError("实际序列必须是一维数组，模拟路径必须是二维数组")
        if simulated.shape[1] != len(actual):
            raise ValueError("每条模拟路径长度必须与实际序列一致")
        if simulated.shape[0] < 2:
            raise ValueError("模拟路径数至少为 2")
        index = pd.Index(self.index).copy()
        if len(index) != len(actual):
            raise ValueError("序列索引长度必须与序列长度一致")
        if not np.all(np.isfinite(actual)) or not np.all(np.isfinite(simulated)):
            raise ValueError("实际序列和模拟路径必须只包含有限值")
        if isinstance(self.seed, bool) or not isinstance(self.seed, (int, np.integer)):
            raise TypeError("seed 必须是整数")
        if isinstance(self.confidence_level, bool):
            raise TypeError("confidence_level 必须是 0 到 1 之间的数字")
        try:
            confidence_level = float(self.confidence_level)
        except (TypeError, ValueError) as exc:
            raise TypeError("confidence_level 必须是 0 到 1 之间的数字") from exc
        if not 0.0 < confidence_level < 1.0:
            raise ValueError("confidence_level 必须严格位于 0 和 1 之间")
        if isinstance(self.acf_lags, bool) or not isinstance(
            self.acf_lags, (int, np.integer)
        ):
            raise TypeError("acf_lags 必须是正整数")
        acf_lags = min(int(self.acf_lags), len(actual) - 2)
        if acf_lags < 1:
            raise ValueError("实际序列至少需要 3 个观测值才能比较 ACF")

        actual_acf = _sample_acf(actual, acf_lags)
        simulated_acf = np.vstack(
            [_sample_acf(path, acf_lags) for path in simulated]
        )
        object.__setattr__(self, "actual", actual.copy())
        object.__setattr__(self, "simulated", simulated.copy())
        object.__setattr__(self, "index", index)
        object.__setattr__(self, "seed", int(self.seed))
        object.__setattr__(self, "confidence_level", confidence_level)
        object.__setattr__(self, "acf_lags", acf_lags)
        object.__setattr__(self, "_actual_acf", actual_acf)
        object.__setattr__(self, "_simulated_acf", simulated_acf)

    @property
    def n_paths(self) -> int:
        """返回模拟路径数量。"""
        return int(self.simulated.shape[0])

    @property
    def simulated_median(self) -> np.ndarray:
        """返回每个时点的模拟中位数。"""
        return np.quantile(self.simulated, 0.5, axis=0)

    @property
    def simulated_lower(self) -> np.ndarray:
        """返回每个时点的模拟区间下界。"""
        return np.quantile(self.simulated, self._tail_probability, axis=0)

    @property
    def simulated_upper(self) -> np.ndarray:
        """返回每个时点的模拟区间上界。"""
        return np.quantile(self.simulated, 1.0 - self._tail_probability, axis=0)

    @property
    def _tail_probability(self) -> float:
        """返回中心模拟区间的单侧尾部概率。"""
        return (1.0 - self.confidence_level) / 2.0

    @property
    def pointwise_coverage(self) -> float:
        """返回实际序列落在逐时模拟区间内的比例。"""
        inside = (self.actual >= self.simulated_lower) & (
            self.actual <= self.simulated_upper
        )
        return float(np.mean(inside))

    @property
    def actual_mean(self) -> float:
        """返回实际序列均值。"""
        return float(np.mean(self.actual))

    @property
    def simulated_means(self) -> np.ndarray:
        """返回每条模拟路径的均值。"""
        return np.mean(self.simulated, axis=1)

    @property
    def mean_interval(self) -> tuple[float, float]:
        """返回模拟均值的中心区间。"""
        return _central_interval(self.simulated_means, self.confidence_level)

    @property
    def mean_in_interval(self) -> bool:
        """返回实际均值是否落在模拟均值区间内。"""
        return _value_in_interval(self.actual_mean, self.mean_interval)

    @property
    def actual_variance(self) -> float:
        """返回实际序列样本方差。"""
        return float(np.var(self.actual, ddof=1))

    @property
    def simulated_variances(self) -> np.ndarray:
        """返回每条模拟路径的样本方差。"""
        return np.var(self.simulated, axis=1, ddof=1)

    @property
    def variance_interval(self) -> tuple[float, float]:
        """返回模拟方差的中心区间。"""
        return _central_interval(self.simulated_variances, self.confidence_level)

    @property
    def variance_in_interval(self) -> bool:
        """返回实际方差是否落在模拟方差区间内。"""
        return _value_in_interval(self.actual_variance, self.variance_interval)

    @property
    def actual_acf(self) -> np.ndarray:
        """返回实际序列滞后 1 至 ``acf_lags`` 的 ACF。"""
        return self._actual_acf.copy()

    @property
    def simulated_acfs(self) -> np.ndarray:
        """返回每条模拟路径的滞后 ACF。"""
        return self._simulated_acf.copy()

    @property
    def simulated_acf_median(self) -> np.ndarray:
        """返回各滞后期模拟 ACF 的中位数。"""
        return np.quantile(self._simulated_acf, 0.5, axis=0)

    @property
    def simulated_acf_lower(self) -> np.ndarray:
        """返回各滞后期模拟 ACF 区间下界。"""
        return np.quantile(self._simulated_acf, self._tail_probability, axis=0)

    @property
    def simulated_acf_upper(self) -> np.ndarray:
        """返回各滞后期模拟 ACF 区间上界。"""
        return np.quantile(
            self._simulated_acf,
            1.0 - self._tail_probability,
            axis=0,
        )

    @property
    def acf_coverage(self) -> float:
        """返回实际 ACF 落入对应模拟区间的滞后期比例。"""
        inside = (self.actual_acf >= self.simulated_acf_lower) & (
            self.actual_acf <= self.simulated_acf_upper
        )
        return float(np.mean(inside))

    @property
    def acf_in_interval(self) -> bool:
        """返回所有比较滞后期的实际 ACF 是否都落在模拟区间内。"""
        return bool(np.isclose(self.acf_coverage, 1.0))

    @property
    def actual_turning_points(self) -> int:
        """返回实际序列的严格局部极值数量。"""
        return _count_turning_points(self.actual)

    @property
    def simulated_turning_points(self) -> np.ndarray:
        """返回每条模拟路径的严格局部极值数量。"""
        return np.asarray(
            [_count_turning_points(path) for path in self.simulated],
            dtype=float,
        )

    @property
    def turning_points_interval(self) -> tuple[float, float]:
        """返回模拟转折点数量的中心区间。"""
        return _central_interval(
            self.simulated_turning_points,
            self.confidence_level,
        )

    @property
    def turning_points_in_interval(self) -> bool:
        """返回实际转折点数量是否落在模拟区间内。"""
        return _value_in_interval(
            self.actual_turning_points,
            self.turning_points_interval,
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
    n_paths: int = 500,
    seed: int = 42,
    confidence_level: float = 0.95,
    acf_lags: int = 10,
) -> SARIMAXSimulationComparison:
    """根据已估计的纯 SARIMAX 参数生成多条理论模拟路径。

    该函数把拟合结果中的趋势和静态外生变量贡献作为确定性路径，
    再重复调用 ``TsSims.simulate_sarimax`` 生成同长度的 SARIMA 随机误差。
    ``log=True`` 时，每条路径都在 log 尺度完成模拟，最后还原到原始响应尺度。
    返回对象同时计算逐时覆盖率、均值、方差、ACF 和转折点数量的模拟分布。

    Parameters
    ----------
    result : SARIMAXResult
        已拟合的纯 SARIMAX 结果；自动选阶结果应先传入其最佳模型。
    n_paths : int, default=500
        要生成的独立模拟路径数量，至少为 2。
    seed : int, default=42
        模拟路径使用的基础随机种子；相同拟合结果、路径数和种子会产生相同结果。
    confidence_level : float, default=0.95
        逐时模拟区间和统计量模拟区间的中心置信水平。
    acf_lags : int, default=10
        ACF 比较的最大滞后阶数；实际使用值不超过样本量减 2。

    Returns
    -------
    SARIMAXSimulationComparison
        包含实际序列、模拟路径矩阵、共同索引和多项分布比较结果的对象。

    Raises
    ------
    ValueError
        结果不是纯 SARIMAX、参数不完整、输入范围无效、序列长度不一致或
        模拟结果无效时。
    TypeError
        ``n_paths``、``seed``、``confidence_level`` 或 ``acf_lags`` 类型无效时。
    """
    if getattr(result, "model_type", None) != "SARIMAX":
        raise ValueError("理论模拟图只支持纯 SARIMAX 模型")
    if getattr(result, "distributed_lag_names", ()):
        raise ValueError("理论模拟图不支持带传递函数的 RDL 模型")
    if isinstance(n_paths, bool) or not isinstance(n_paths, (int, np.integer)):
        raise TypeError("n_paths 必须是整数")
    if int(n_paths) < 2:
        raise ValueError("n_paths 至少为 2")
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
        raise TypeError("seed 必须是整数")
    if int(seed) < 0:
        raise ValueError("seed 必须是非负整数")

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
    path_seeds = np.random.SeedSequence(int(seed)).generate_state(int(n_paths))
    simulated_paths = []
    for path_seed in path_seeds:
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
            seed=int(path_seed),
        )
        path = np.asarray(simulation.data, dtype=float)
        if getattr(result, "log", False):
            with np.errstate(over="ignore", invalid="ignore"):
                path = np.exp(path)
        if path.ndim != 1 or len(path) != nobs:
            raise ValueError("理论模拟路径长度与实际建模序列不一致")
        if not np.all(np.isfinite(path)):
            raise ValueError("理论模拟路径包含非有限值")
        simulated_paths.append(path)

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
        simulated=np.vstack(simulated_paths),
        index=index,
        seed=int(seed),
        confidence_level=confidence_level,
        acf_lags=acf_lags,
    )


def build_sarimax_simulation_summary(
    comparison: SARIMAXSimulationComparison,
) -> pd.DataFrame:
    """整理均值、方差和转折点数量的实际值与模拟区间。

    Parameters
    ----------
    comparison : SARIMAXSimulationComparison
        已生成的实际序列和多条模拟路径比较对象。

    Returns
    -------
    pandas.DataFrame
        每个统计量一行，包含实际值、模拟中心区间和是否落入区间。
    """
    level = f"{comparison.confidence_level:.0%}"
    rows = (
        (
            "均值",
            comparison.actual_mean,
            *comparison.mean_interval,
            comparison.mean_in_interval,
        ),
        (
            "方差（样本方差）",
            comparison.actual_variance,
            *comparison.variance_interval,
            comparison.variance_in_interval,
        ),
        (
            "转折点数量",
            float(comparison.actual_turning_points),
            *comparison.turning_points_interval,
            comparison.turning_points_in_interval,
        ),
    )
    return pd.DataFrame(
        rows,
        columns=(
            "统计量",
            "实际值",
            f"模拟{level}下界",
            f"模拟{level}上界",
            "是否落入模拟区间",
        ),
    )


def build_sarimax_acf_comparison_table(
    comparison: SARIMAXSimulationComparison,
) -> pd.DataFrame:
    """整理实际 ACF 与各滞后期模拟 ACF 区间。

    Parameters
    ----------
    comparison : SARIMAXSimulationComparison
        已生成的实际序列和多条模拟路径比较对象。

    Returns
    -------
    pandas.DataFrame
        每个滞后期一行，包含实际 ACF、模拟中位数、模拟区间和判定。
    """
    inside = (comparison.actual_acf >= comparison.simulated_acf_lower) & (
        comparison.actual_acf <= comparison.simulated_acf_upper
    )
    level = f"{comparison.confidence_level:.0%}"
    return pd.DataFrame(
        {
            "滞后期数": np.arange(1, comparison.acf_lags + 1),
            "实际 ACF": comparison.actual_acf,
            "模拟中位数": comparison.simulated_acf_median,
            f"模拟{level}下界": comparison.simulated_acf_lower,
            f"模拟{level}上界": comparison.simulated_acf_upper,
            "是否落入模拟区间": np.where(inside, "是", "否"),
        }
    )


__all__ = [
    "SARIMAXSimulationComparison",
    "build_sarimax_acf_comparison_table",
    "build_sarimax_simulation_comparison",
    "build_sarimax_simulation_summary",
]
