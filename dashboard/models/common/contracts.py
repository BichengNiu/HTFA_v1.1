"""模型估计工作流的稳定输入和结果协议。

这些对象只描述跨模型可观察的行为，不导入 Streamlit 或 Ts 的具体结果类。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


def _normalise_window(
    value: tuple[Any, Any] | list[Any] | None,
) -> tuple[Any, Any] | None:
    if value is None:
        return None
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError("训练范围必须是包含起止值的二元组")
    start, end = value
    if isinstance(start, (pd.Timestamp, str)) or isinstance(
        end, (pd.Timestamp, str)
    ):
        try:
            start, end = pd.Timestamp(start), pd.Timestamp(end)
        except (TypeError, ValueError) as exc:
            raise ValueError("训练范围包含无效日期") from exc
        if pd.isna(start) or pd.isna(end):
            raise ValueError("训练范围包含无效日期")
    try:
        if start > end:
            raise ValueError("训练起始值不能晚于结束值")
    except TypeError as exc:
        raise ValueError("训练范围的起止值必须可比较") from exc
    return start, end


@dataclass(frozen=True)
class ModelingInput:
    """跨模型共享的、已经完成对齐的建模输入。

    Parameters
    ----------
    series : pandas.Series
        目标变量序列。
    exog : pandas.DataFrame or None
        可选的外生变量表。
    index : pandas.Index
        与目标和外生变量对齐的建模索引。
    target : str
        目标变量名称。
    exog_names : tuple[str, ...]
        外生变量名称，顺序必须与 ``exog`` 列顺序一致。
    training_range : tuple or None
        用户选择的闭区间训练范围。
    dataset_fingerprint : str
        原始数据集身份指纹。
    preprocessing : tuple[str, ...]
        已应用的预处理规则。
    response_log : bool
        是否对目标变量应用对数变换。
    """

    series: pd.Series
    exog: pd.DataFrame | None
    index: pd.Index
    target: str
    exog_names: tuple[str, ...] = ()
    training_range: tuple[Any, Any] | None = None
    dataset_fingerprint: str = ""
    preprocessing: tuple[str, ...] = ()
    response_log: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.series, pd.Series):
            raise TypeError("series 必须是 pandas.Series")
        if not isinstance(self.target, str) or not self.target.strip():
            raise ValueError("target 必须是非空字符串")
        index = pd.Index(self.index).copy()
        if not self.series.index.equals(index):
            raise ValueError("目标序列与建模索引不一致")
        exog_names = tuple(str(name) for name in self.exog_names)
        if self.exog is None:
            if exog_names:
                raise ValueError("没有外生变量表时不能提供 exog_names")
        else:
            if not isinstance(self.exog, pd.DataFrame):
                raise TypeError("exog 必须是 pandas.DataFrame 或 None")
            if not self.exog.index.equals(index):
                raise ValueError("外生变量与建模索引不一致")
            if tuple(map(str, self.exog.columns)) != exog_names:
                raise ValueError("exog_names 与外生变量列不一致")
        if not isinstance(self.response_log, bool):
            raise TypeError("response_log 必须是布尔值")
        object.__setattr__(self, "series", self.series.copy(deep=True))
        object.__setattr__(
            self,
            "exog",
            None if self.exog is None else self.exog.copy(deep=True),
        )
        object.__setattr__(self, "index", index)
        object.__setattr__(self, "exog_names", exog_names)
        object.__setattr__(
            self,
            "training_range",
            _normalise_window(self.training_range),
        )
        object.__setattr__(
            self,
            "preprocessing",
            tuple(str(item) for item in self.preprocessing),
        )


@dataclass(frozen=True)
class ForecastRequest:
    """跨模型共享的预测请求。

    Parameters
    ----------
    start : int or datetime-like
        预测起点。
    end : int or datetime-like
        预测终点，包含终点。
    alpha : float, default=0.05
        预测区间显著性水平，必须严格位于 0 和 1 之间。
    dynamic : bool, default=False
        是否请求动态预测。
    future_exog : pandas.DataFrame or None, optional
        样本外外生变量路径。
    future_dates : pandas.DatetimeIndex or None, optional
        样本外日期路径。
    """

    start: int | str | pd.Timestamp
    end: int | str | pd.Timestamp
    alpha: float = 0.05
    dynamic: bool = False
    future_exog: pd.DataFrame | None = None
    future_dates: pd.DatetimeIndex | None = None

    def __post_init__(self) -> None:
        if isinstance(self.start, bool) or isinstance(self.end, bool):
            raise TypeError("预测起止值不能是布尔值")
        if not isinstance(self.alpha, (int, float)) or not 0.0 < self.alpha < 1.0:
            raise ValueError("alpha 必须严格位于 0 和 1 之间")
        if not isinstance(self.dynamic, bool):
            raise TypeError("dynamic 必须是布尔值")
        try:
            if self.start > self.end:
                raise ValueError("预测起始值不能晚于结束值")
        except TypeError as exc:
            raise ValueError("预测起止值必须可比较") from exc
        if self.future_exog is not None and not isinstance(
            self.future_exog, pd.DataFrame
        ):
            raise TypeError("future_exog 必须是 pandas.DataFrame 或 None")
        if self.future_dates is not None:
            dates = pd.DatetimeIndex(pd.to_datetime(self.future_dates))
            if dates.hasnans:
                raise ValueError("future_dates 不能包含无效日期")
            object.__setattr__(self, "future_dates", dates)
        if self.future_exog is not None:
            object.__setattr__(
                self,
                "future_exog",
                self.future_exog.copy(deep=True),
            )
        object.__setattr__(self, "alpha", float(self.alpha))


@dataclass(frozen=True)
class ForecastResult:
    """统一预测结果，表格和图形必须共同消费该对象。

    Parameters
    ----------
    dates : pandas.DatetimeIndex or None
        预测日期；无日期模型可以传 ``None``。
    mean : array-like
        预测均值。
    lower : array-like
        预测区间下界。
    upper : array-like
        预测区间上界。
    alpha : float
        预测区间显著性水平。
    steps : int
        预测期数。
    start : int or datetime-like
        预测起点。
    end : int or datetime-like
        预测终点。
    prediction : object
        底层预测对象，仅供模型专属绘图适配层使用。
    """

    dates: pd.DatetimeIndex | None
    mean: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    alpha: float
    steps: int
    start: Any
    end: Any
    prediction: Any = field(repr=False)

    def __post_init__(self) -> None:
        if isinstance(self.steps, bool) or not isinstance(
            self.steps, (int, np.integer)
        ):
            raise TypeError("steps 必须是整数")
        steps = int(self.steps)
        if steps < 0:
            raise ValueError("steps 不能为负数")
        arrays = {
            "mean": np.asarray(self.mean, dtype=float),
            "lower": np.asarray(self.lower, dtype=float),
            "upper": np.asarray(self.upper, dtype=float),
        }
        if any(array.ndim != 1 for array in arrays.values()):
            raise ValueError("预测数组必须是一维")
        lengths = {len(array) for array in arrays.values()}
        if len(lengths) != 1 or steps != len(arrays["mean"]):
            raise ValueError("预测数组长度、steps 必须一致")
        if any(not np.isfinite(array).all() for array in arrays.values()):
            raise ValueError("预测结果包含非有限值")
        if np.any(arrays["lower"] > arrays["mean"]) or np.any(
            arrays["mean"] > arrays["upper"]
        ):
            raise ValueError("预测区间必须满足下界 <= 均值 <= 上界")
        if not isinstance(self.alpha, (int, float)) or not 0.0 < self.alpha < 1.0:
            raise ValueError("alpha 必须严格位于 0 和 1 之间")
        object.__setattr__(self, "steps", steps)
        dates = self.dates
        if dates is not None:
            dates = pd.DatetimeIndex(pd.to_datetime(dates))
            if len(dates) != steps or dates.hasnans:
                raise ValueError("预测日期与预测数组长度不一致")
            object.__setattr__(self, "dates", dates)
        for name, array in arrays.items():
            object.__setattr__(self, name, array.copy())
        object.__setattr__(self, "alpha", float(self.alpha))


@dataclass(frozen=True)
class EstimationResultView:
    """供通用估计结果模块展示的稳定视图。

    ``result`` 是不透明的底层结果，仅由模型适配器或特有诊断扩展使用；
    通用展示依赖其余字段，不判断具体底层结果类型。
    """

    model_name: str
    result: Any = field(repr=False)
    converged: bool
    effective_nobs: int
    optimizer: str | None
    aic: float
    bic: float
    log_likelihood: float
    summary: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    selection_title: str | None = None
    selection_message: str | None = None
    selection_table: pd.DataFrame | None = None
    selected_label: str | None = None
    selection_options: tuple[Any, ...] = ()
    selection_value: Any = None
    selection_help: str | None = None
    candidate_options: tuple[Any, ...] = ()
    candidate_value: Any = None
    candidate_help: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.model_name, str) or not self.model_name.strip():
            raise ValueError("model_name 必须是非空字符串")
        if isinstance(self.effective_nobs, bool) or not isinstance(
            self.effective_nobs, (int, np.integer)
        ) or self.effective_nobs < 0:
            raise ValueError("effective_nobs 必须是非负整数")
        if not isinstance(self.converged, bool):
            raise TypeError("converged 必须是布尔值")
        object.__setattr__(self, "effective_nobs", int(self.effective_nobs))
        object.__setattr__(self, "metadata", dict(self.metadata))
        if self.selection_table is not None:
            object.__setattr__(
                self,
                "selection_table",
                self.selection_table.copy(deep=True),
            )


@dataclass(frozen=True)
class ResidualDiagnosticView:
    """供模型专属诊断展示使用的稳定上下文。

    ``figure`` 是不透明的绘图对象，由模型适配器负责创建；页面只负责
    将它交给现有绘图渲染器。残差数量和滞后阶数也在适配器内确定，避免
    页面读取底层模型结果的具体属性。

    Parameters
    ----------
    effective_nobs : int
        残差中参与诊断的有限观测数。
    lags : int
        残差检验使用的最大滞后阶数。
    figure : object or None
        已准备好的诊断图对象；绘图失败时为 ``None``。
    figure_error : str or None, optional
        诊断图准备失败时的可展示错误信息。
    """

    effective_nobs: int
    lags: int
    figure: Any = field(default=None, repr=False)
    figure_error: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.effective_nobs, bool) or not isinstance(
            self.effective_nobs, (int, np.integer)
        ) or self.effective_nobs < 0:
            raise ValueError("effective_nobs 必须是非负整数")
        if isinstance(self.lags, bool) or not isinstance(
            self.lags, (int, np.integer)
        ) or self.lags < 1:
            raise ValueError("lags 必须是正整数")
        if self.figure_error is not None and not isinstance(
            self.figure_error, str
        ):
            raise TypeError("figure_error 必须是字符串或 None")
        object.__setattr__(self, "effective_nobs", int(self.effective_nobs))
        object.__setattr__(self, "lags", int(self.lags))


__all__ = [
    "EstimationResultView",
    "ForecastRequest",
    "ForecastResult",
    "ModelingInput",
    "ResidualDiagnosticView",
]
