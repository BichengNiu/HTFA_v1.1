"""单变量平稳性诊断、预处理与检验。

本模块只包含可测试的统计逻辑。Streamlit 状态和组件渲染位于
``dashboard.explore.ui.stationarity``。
"""

from __future__ import annotations

import logging
import warnings
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import MaxNLocator
from Ts import TimeSeriesSummary, difference
from Ts.TsPlots import plot_acf, plot_pacf, plot_series
from Ts.TsTests import (
    ADFTest,
    KPSSTest,
    PhillipsPerronTest,
)

from dashboard.explore.core.constants import (
    MIN_SAMPLES_ADF,
    SEASONAL_DIFF_MAP,
)
from dashboard.explore.core.series_utils import (
    identify_time_column,
    prepare_time_index,
)

logger = logging.getLogger(__name__)

_GRID_LINE_STYLES = {
    "solid": "-",
    "dashed": "--",
    "dotted": ":",
    "dashdot": "-.",
}


@contextmanager
def matplotlib_date_compatibility():
    """隔离 Matplotlib 与 NumPy 2.5 日期转换的第三方弃用警告。"""
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"The 'generic' unit for NumPy timedelta is deprecated",
            category=DeprecationWarning,
            module=r"matplotlib\.dates",
        )
        yield


@dataclass(frozen=True)
class TransformationSpec:
    """一个可供界面选择的序列变换。"""

    label: str
    order: int | None = None
    log: bool = False
    year_over_year: bool = False


TRANSFORMATIONS: dict[str, TransformationSpec] = {
    "original": TransformationSpec("不处理"),
    "log": TransformationSpec("对数", log=True),
    "first_difference": TransformationSpec("一阶差分", order=1),
    "second_difference": TransformationSpec("二阶差分", order=2),
    "year_over_year": TransformationSpec(
        "同比差分",
        order=1,
        year_over_year=True,
    ),
    "log_first_difference": TransformationSpec(
        "对数一阶差分",
        order=1,
        log=True,
    ),
    "log_second_difference": TransformationSpec(
        "对数二阶差分",
        order=2,
        log=True,
    ),
    "log_year_over_year": TransformationSpec(
        "对数同比差分",
        order=1,
        log=True,
        year_over_year=True,
    ),
}


TABLE_FREQUENCIES = {
    "daily": "Daily",
    "weekly": "Weekly",
    "ten_day": "Ten_Day",
    "monthly": "Monthly",
    "quarterly": "Quarterly",
    "yearly": "Annual",
    "annual": "Annual",
    "table": "Undetermined",
}


YEAR_OVER_YEAR_LAGS = {
    frequency: lag
    for frequency, lag in SEASONAL_DIFF_MAP.items()
    if lag is not None
}


TEST_LABELS = {
    "adf": "ADF 检验",
    "kpss": "KPSS 检验",
    "pp": "Phillips–Perron 检验",
}


TEST_NULL_HYPOTHESES = {
    "adf": "序列存在单位根（非平稳）",
    "kpss": "序列平稳",
    "pp": "序列存在单位根（非平稳）",
}


TEST_TREND_OPTIONS = {
    "adf": ("n", "c", "ct", "ctt"),
    "kpss": ("c", "ct"),
    "pp": ("c", "ct"),
}


TEST_TREND_LABELS = {
    "adf": {
        "n": "无常数项",
        "c": "常数项",
        "ct": "常数项 + 线性趋势",
        "ctt": "常数项 + 线性趋势 + 二次趋势",
    },
    "kpss": {
        "c": "水平平稳（常数项）",
        "ct": "趋势平稳（常数项 + 线性趋势）",
    },
    "pp": {
        "c": "常数项",
        "ct": "常数项 + 线性趋势",
    },
}


RESULT_COLUMNS = [
    "检验代码",
    "检验",
    "确定性项",
    "原假设",
    "统计量",
    "P值",
    "滞后阶数",
    "有效样本数",
    "临界值",
    "判定",
    "平稳性解释",
    "错误",
]


SUMMARY_LABELS = {
    "Name": "名称",
    "Observations": "总观测数",
    "Valid observations": "有效观测数",
    "Frequency": "频率",
    "Start": "起始时间",
    "End": "结束时间",
    "Missing values": "缺失值数",
    "Missing ratio": "缺失比例",
    "Missing timestamps": "缺失时间点",
    "Missing positions": "缺失位置",
    "Mean": "均值",
    "Standard deviation": "标准差",
    "Minimum": "最小值",
    "First quartile": "第一四分位数",
    "Median": "中位数",
    "Third quartile": "第三四分位数",
    "Maximum": "最大值",
}


def _validate_numeric_series(series: pd.Series) -> pd.Series:
    """验证并返回浮点副本，不静默改变索引或缺失位置。"""
    if not isinstance(series, pd.Series):
        raise TypeError("分析对象必须是 pandas.Series")
    if series.empty:
        raise ValueError("序列不能为空")
    if (
        not pd.api.types.is_numeric_dtype(series.dtype)
        or pd.api.types.is_bool_dtype(series.dtype)
        or pd.api.types.is_complex_dtype(series.dtype)
    ):
        raise TypeError("序列必须是实数型变量")

    converted = series.astype(float)
    values = converted.to_numpy(dtype=float, na_value=np.nan)
    if np.isinf(values).any():
        raise ValueError("序列包含无穷值")
    return converted


def numeric_variable_names(data: pd.DataFrame) -> list[str]:
    """按原始列顺序返回可分析的实数型变量。"""
    return [
        column
        for column in data.columns
        if pd.api.types.is_numeric_dtype(data[column].dtype)
        and not pd.api.types.is_bool_dtype(data[column].dtype)
        and not pd.api.types.is_complex_dtype(data[column].dtype)
    ]


def prepare_selected_series(
    data: pd.DataFrame,
    variable: str,
) -> tuple[pd.Series, str | None]:
    """提取变量并尽可能建立经过校验的升序时间索引。"""
    if variable not in data.columns:
        raise KeyError(f"数据表中不存在变量: {variable}")
    if variable not in numeric_variable_names(data):
        raise TypeError(f"变量“{variable}”不是可分析的实数型变量")

    time_column = identify_time_column(data, exclude_columns=[variable])
    if time_column is None and not isinstance(data.index, pd.DatetimeIndex):
        prepared, time_label = data.copy(), None
    else:
        prepared, time_label = prepare_time_index(
            data,
            time_column=time_column,
            set_as_index=True,
            keep_column=False,
        )
    series = _validate_numeric_series(prepared[variable])
    if isinstance(series.index, pd.DatetimeIndex):
        if series.index.isna().any():
            raise ValueError("时间列包含无法解析的日期")
        if series.index.duplicated().any():
            raise ValueError("时间列包含重复日期")
        series = series.sort_index()
    return series, time_label


def normalize_frequency(frequency: str | None) -> str:
    """将频率表键和显示名称统一为内部频率名称。"""
    if frequency is None:
        return "Undetermined"
    value = str(frequency).strip()
    if value in YEAR_OVER_YEAR_LAGS or value in {"Daily", "Undetermined"}:
        return value
    return TABLE_FREQUENCIES.get(value.lower(), value)


def resolve_year_over_year_lag(frequency: str | None) -> int:
    """返回同比差分期数；不可靠的频率不做主观推断。"""
    normalized = normalize_frequency(frequency)
    lag = YEAR_OVER_YEAR_LAGS.get(normalized)
    if lag is None:
        raise ValueError(
            f"频率“{normalized}”不支持同比差分；"
            "请选择具有明确年内期数的周度、旬度、月度、季度或年度表"
        )
    return lag


def transform_series(
    series: pd.Series,
    transformation: str,
    *,
    frequency: str | None = None,
) -> pd.Series:
    """使用 ``Ts.difference`` 执行界面支持的序列变换。"""
    values = _validate_numeric_series(series)
    try:
        spec = TRANSFORMATIONS[transformation]
    except KeyError as exc:
        raise ValueError(f"未知预处理方法: {transformation}") from exc

    if spec.order is None and not spec.log:
        return values.copy()

    if spec.log and (values.dropna() <= 0).any():
        raise ValueError("对数处理要求所有非缺失观测严格大于 0")

    if spec.order is None:
        transformed = np.log(values)
        transformed.name = series.name
        return transformed

    lag = resolve_year_over_year_lag(frequency) if spec.year_over_year else 1
    transformed = difference(
        values,
        order=spec.order,
        log=spec.log,
        lag=lag,
    )
    transformed.name = series.name
    return transformed


def _localize_summary_frequency(value: str) -> str:
    normalized = value.strip()
    upper = normalized.upper()
    if upper.startswith(("QE", "Q-")) or upper == "Q":
        return "季度"
    if upper.startswith(("ME", "MS", "M-", "WOM")) or upper == "M":
        return "月度"
    if upper.startswith("W"):
        return "周度"
    if upper.startswith(("YE", "YS", "A-", "Y-")) or upper in {"A", "Y"}:
        return "年度"
    if upper.startswith(("D", "B")):
        return "日度"
    if normalized == "irregular or unknown":
        return "不规则或未知"
    if normalized == "unknown":
        return "未知"
    if normalized.startswith("positional"):
        return normalized.replace("positional", "位置索引").replace(
            "step",
            "步长",
        )
    return normalized


def localize_summary_text(summary: str) -> str:
    """将 ``Ts.summary()`` 的固定英文标签完整转换为中文。"""
    localized = []
    for line in summary.splitlines():
        stripped = line.strip()
        if stripped == "Time Series Summary":
            localized.append("时间序列统计摘要")
            continue
        if ":" not in line:
            localized.append(line)
            continue
        label, value = line.split(":", 1)
        english_label = label.strip()
        chinese_label = SUMMARY_LABELS.get(english_label, english_label)
        localized_value = value.strip()
        if english_label == "Frequency":
            localized_value = _localize_summary_frequency(localized_value)
        elif localized_value == "None":
            localized_value = "无"
        elif localized_value == "Unnamed":
            localized_value = "未命名"
        localized.append(f"{chinese_label}：{localized_value}")
    return "\n".join(localized)


SUMMARY_FREQUENCY_LABELS = {
    "Daily": "日度",
    "Weekly": "周度",
    "Ten_Day": "旬度",
    "Monthly": "月度",
    "Quarterly": "季度",
    "Annual": "年度",
    "Undetermined": "未确定",
}


def summarize_series(
    series: pd.Series,
    *,
    alpha: float = 0.05,
    frequency: str | None = None,
) -> str:
    """调用 ``Ts.TimeSeriesSummary.summary`` 并转换为中文摘要。

    ``frequency`` 非空时使用调用方已经确认的业务频率，避免 Ts 的索引推断
    与工作簿元数据/频率表口径不一致。
    """
    values = _validate_numeric_series(series)
    summary = TimeSeriesSummary(values, alpha=alpha).summary(plot=False)
    localized = localize_summary_text(summary)
    if frequency is None:
        return localized

    display_frequency = SUMMARY_FREQUENCY_LABELS.get(frequency, str(frequency))
    lines = localized.splitlines()
    return "\n".join(
        f"频率：{display_frequency}" if line.startswith("频率：") else line
        for line in lines
    )


def create_time_series_figure(
    series: pd.Series,
    *,
    title: str | None = None,
    x_title: str = "时间",
    y_title: str | None = None,
    line_width: float = 3,
    marker_size: float = 0,
    max_ticks: int = 12,
    y_tick_count: int = 8,
    x_start=None,
    y_start: float | None = None,
    grid_mode: str = "both",
    grid_line_style: str = "solid",
    grid: bool | None = None,
    ymin: float | None = None,
):
    """使用 ``Ts.TsPlots.plot_series`` 绘制时间序列。"""
    values = _validate_numeric_series(series)
    if y_start is None:
        y_start = ymin
    if grid is not None:
        grid_mode = "both" if grid else "none"
    with matplotlib_date_compatibility():
        figure, axis = plot_series(
            values,
            title=title,
            xtitle=x_title,
            ytitle=y_title or str(series.name or "数值"),
            linewidth=line_width,
            markersize=marker_size,
            max_ticks=max_ticks,
            grid=False,
            ymin=y_start,
            show_legend=False,
        )
        _apply_axis_options(
            axis,
            x_start=x_start,
            y_start=y_start,
            x_tick_count=max_ticks,
            y_tick_count=y_tick_count,
            grid_mode=grid_mode,
            grid_line_style=grid_line_style,
            date_x_axis=isinstance(values.index, pd.DatetimeIndex),
        )
    return figure


def resolve_correlation_lags(
    series: pd.Series,
    requested: int | None = None,
) -> tuple[int, int]:
    """返回 ``(实际滞后阶数, PACF 最大允许阶数)``。"""
    values = _validate_numeric_series(series).dropna()
    maximum = len(values) // 2 - 1
    if maximum < 1:
        raise ValueError("ACF/PACF 至少需要 4 个有效观测")

    if requested is None:
        return min(40, maximum), maximum
    if isinstance(requested, bool) or not isinstance(
        requested,
        (int, np.integer),
    ):
        raise TypeError("滞后阶数必须是正整数")
    requested = int(requested)
    if requested < 1:
        raise ValueError("滞后阶数必须至少为 1")
    if requested > maximum:
        raise ValueError(f"当前有效样本下，PACF 滞后阶数最大允许值为 {maximum}")
    return requested, maximum


def _apply_axis_options(
    axis,
    *,
    x_start=None,
    y_start: float | None = None,
    x_tick_count: int = 12,
    y_tick_count: int = 8,
    grid_mode: str = "both",
    grid_line_style: str = "solid",
    date_x_axis: bool = False,
) -> None:
    """将坐标轴范围、刻度数量和网格方向统一应用到单个坐标轴。"""
    if x_start is not None:
        axis.set_xlim(left=x_start)
    if y_start is not None:
        axis.set_ylim(bottom=y_start)
    if not date_x_axis:
        axis.xaxis.set_major_locator(MaxNLocator(nbins=max(2, int(x_tick_count))))
    axis.yaxis.set_major_locator(MaxNLocator(nbins=max(2, int(y_tick_count))))
    try:
        line_style = _GRID_LINE_STYLES[grid_line_style]
    except KeyError as exc:
        raise ValueError(f"未知网格线型: {grid_line_style}") from exc
    axis.grid(False)
    if grid_mode == "horizontal":
        axis.yaxis.grid(True, linestyle=line_style)
    elif grid_mode == "vertical":
        axis.xaxis.grid(True, linestyle=line_style)
    elif grid_mode == "both":
        axis.grid(True, linestyle=line_style)
    elif grid_mode != "none":
        raise ValueError(f"未知网格方向: {grid_mode}")


def create_correlogram_figure(
    series: pd.Series,
    *,
    nlags: int | None = None,
    alpha: float = 0.05,
    title_prefix: str | None = None,
    include_acf: bool = True,
    include_pacf: bool = True,
    acf_title: str | None = None,
    pacf_title: str | None = None,
    acf_x_title: str = "滞后期数",
    acf_y_title: str = "ACF值",
    pacf_x_title: str = "滞后期数",
    pacf_y_title: str = "PACF值",
    max_ticks: int = 12,
    y_tick_count: int = 8,
    x_start: float | None = 0,
    y_start: float | None = None,
    grid_mode: str = "both",
    grid_line_style: str = "solid",
    grid: bool | None = None,
    pacf_method: str = "ywm",
):
    """使用 ``Ts`` 绘制同一序列的 ACF 和 PACF。"""
    if not include_acf and not include_pacf:
        raise ValueError("至少选择绘制 ACF 或 PACF")
    values = _validate_numeric_series(series).dropna()
    if grid is not None:
        grid_mode = "both" if grid else "none"
    resolved_lags, _ = resolve_correlation_lags(values, nlags)
    if values.nunique() <= 1:
        raise ValueError("常数序列无法计算 ACF/PACF")

    prefix = f"{title_prefix} · " if title_prefix else ""
    plotters = []
    if include_acf:
        plotters.append(("ACF", plot_acf))
    if include_pacf:
        plotters.append(("PACF", plot_pacf))
    figure, axes = plt.subplots(
        1,
        len(plotters),
        figsize=(6.5 * len(plotters), 4.5),
        squeeze=False,
    )
    try:
        for axis, (label, plotter) in zip(axes.flat, plotters, strict=True):
            plot_kwargs = {
                "nlags": resolved_lags,
                "alpha": alpha,
                "title": (
                    acf_title if label == "ACF" and acf_title is not None
                    else pacf_title if label == "PACF" and pacf_title is not None
                    else f"{prefix}{label}"
                ),
                "xtitle": acf_x_title if label == "ACF" else pacf_x_title,
                "ytitle": acf_y_title if label == "ACF" else pacf_y_title,
                "max_ticks": max_ticks,
                "grid": False,
                "ax": axis,
            }
            if label == "ACF":
                plot_kwargs["zero_lag"] = False
            else:
                plot_kwargs["method"] = pacf_method
            plotter(
                values,
                **plot_kwargs,
            )
            _apply_axis_options(
                axis,
                x_start=x_start,
                y_start=y_start,
                x_tick_count=max_ticks,
                y_tick_count=y_tick_count,
                grid_mode=grid_mode,
                grid_line_style=grid_line_style,
            )
        figure.tight_layout()
        return figure
    except Exception:
        plt.close(figure)
        raise


def _clean_for_inference(series: pd.Series) -> pd.Series:
    values = _validate_numeric_series(series).dropna()
    if len(values) < MIN_SAMPLES_ADF:
        raise ValueError(
            f"平稳性检验至少需要 {MIN_SAMPLES_ADF} 个有效观测，"
            f"当前只有 {len(values)} 个"
        )
    if values.nunique() <= 1:
        raise ValueError("常数序列无法进行平稳性检验")
    return values


def _maximum_test_lags(nobs: int) -> int:
    return min(8, max(1, nobs // 5))


def _build_test(test_key: str, values: pd.Series, trend: str):
    """将统一界面参数映射到各个 ``TsTests`` 构造器。"""
    max_lags = _maximum_test_lags(len(values))
    if test_key == "adf":
        if len(values) < 20:
            return ADFTest(values, trend=trend, lags=0)
        return ADFTest(values, trend=trend, max_lags=max_lags)
    if test_key == "kpss":
        return KPSSTest(values, trend=trend, nlags="auto")
    if test_key == "pp":
        return PhillipsPerronTest(values, trend=trend)
    raise ValueError(f"未知平稳性检验: {test_key}")


def _alpha_label(alpha: float) -> str:
    return f"{alpha * 100:g}%"


def _critical_value(result: Any, alpha: float) -> float | None:
    critical_values = getattr(result, "critical_values", {}) or {}
    value = critical_values.get(_alpha_label(alpha))
    return None if value is None else float(value)


def _test_decision(
    result: Any,
    test_key: str,
    alpha: float,
    critical_value: float | None,
) -> tuple[str, str]:
    pvalue = getattr(result, "pvalue", None)
    if pvalue is not None:
        reject = float(pvalue) < alpha
    elif critical_value is not None:
        reject = float(result.statistic) < critical_value
    else:
        raise ValueError("检验结果既没有 P 值，也没有对应显著性水平的临界值")

    decision = "拒绝原假设" if reject else "不能拒绝原假设"
    if test_key == "kpss":
        interpretation = "支持非平稳" if reject else "支持平稳"
    else:
        interpretation = "支持平稳" if reject else "支持非平稳"
    return decision, interpretation


def _empty_test_row(test_key: str, trend: str) -> dict[str, Any]:
    return {
        "检验代码": test_key,
        "检验": TEST_LABELS[test_key],
        "确定性项": TEST_TREND_LABELS[test_key][trend],
        "原假设": TEST_NULL_HYPOTHESES[test_key],
        "统计量": None,
        "P值": None,
        "滞后阶数": None,
        "有效样本数": None,
        "临界值": None,
        "判定": "无法判断",
        "平稳性解释": "无法判断",
        "错误": "",
    }


def run_selected_stationarity_tests(
    series: pd.Series,
    tests: Iterable[str],
    *,
    alpha: float = 0.05,
    trend: str = "c",
    test_trends: dict[str, str] | None = None,
) -> pd.DataFrame:
    """按用户选择运行多个 ``TsTests``，单项失败不终止其他检验。"""
    selected = list(dict.fromkeys(tests))
    if not selected:
        raise ValueError("至少选择一种平稳性检验")
    unknown = [test for test in selected if test not in TEST_LABELS]
    if unknown:
        raise ValueError(f"未知平稳性检验: {', '.join(unknown)}")
    if not 0 < alpha < 1:
        raise ValueError("显著性水平必须位于 0 和 1 之间")

    values = _clean_for_inference(series)
    resolved_trends = {}
    for test_key in selected:
        selected_trend = (test_trends or {}).get(test_key, trend)
        if selected_trend not in TEST_TREND_OPTIONS[test_key]:
            allowed = ", ".join(TEST_TREND_OPTIONS[test_key])
            raise ValueError(
                f"{TEST_LABELS[test_key]}的确定性项必须是 {allowed}"
            )
        resolved_trends[test_key] = selected_trend

    rows = []
    for test_key in selected:
        selected_trend = resolved_trends[test_key]
        row = _empty_test_row(test_key, selected_trend)
        try:
            test = _build_test(test_key, values, selected_trend)
            result = test.fit()
            critical_value = _critical_value(result, alpha)
            decision, interpretation = _test_decision(
                result,
                test_key,
                alpha,
                critical_value,
            )
            row.update(
                {
                    "统计量": float(result.statistic),
                    "P值": (
                        None
                        if getattr(result, "pvalue", None) is None
                        else float(result.pvalue)
                    ),
                    "滞后阶数": int(result.lags),
                    "有效样本数": int(result.nobs),
                    "临界值": critical_value,
                    "判定": decision,
                    "平稳性解释": interpretation,
                }
            )
        except Exception as exc:  # noqa: BLE001 - isolate one selected statistical test
            logger.warning("%s 执行失败: %s", TEST_LABELS[test_key], exc)
            row["错误"] = str(exc)
        rows.append(row)

    return pd.DataFrame(rows, columns=RESULT_COLUMNS)


def run_stationarity_tests(
    data: pd.DataFrame,
    alpha: float = 0.05,
) -> pd.DataFrame:
    """兼容旧调用：对每个数值变量运行 ADF 与 KPSS。"""
    rows = []
    for variable in numeric_variable_names(data):
        results = run_selected_stationarity_tests(
            data[variable],
            ["adf", "kpss"],
            alpha=alpha,
            trend="ct",
        ).set_index("检验代码")
        adf = results.loc["adf"]
        kpss = results.loc["kpss"]
        conclusions = {adf["平稳性解释"], kpss["平稳性解释"]}
        if conclusions == {"支持平稳"}:
            overall = "平稳"
        elif conclusions == {"支持非平稳"}:
            overall = "非平稳"
        elif "无法判断" in conclusions:
            overall = "无法判断"
        else:
            overall = "结论不一致"
        rows.append(
            {
                "变量名": variable,
                "有效值个数": int(data[variable].notna().sum()),
                "ADF统计量": adf["统计量"],
                "ADF检验P值": adf["P值"],
                "ADF检验结果": adf["平稳性解释"],
                "KPSS统计量": kpss["统计量"],
                "KPSS检验P值": kpss["P值"],
                "KPSS检验结果": kpss["平稳性解释"],
                "综合结论": overall,
            }
        )
    return pd.DataFrame(rows)


def _legacy_single_test(
    series: pd.Series,
    test_key: str,
    alpha: float,
) -> tuple[float | None, str]:
    row = run_selected_stationarity_tests(
        series,
        [test_key],
        alpha=alpha,
        trend="ct",
    ).iloc[0]
    if row["错误"]:
        return None, f"计算失败({row['错误']})"
    is_stationary = row["平稳性解释"] == "支持平稳"
    return row["P值"], "是" if is_stationary else "否"


def run_adf_test(
    series: pd.Series,
    alpha: float = 0.05,
) -> tuple[float | None, str]:
    """兼容旧调用的 ADF 二元结果。"""
    return _legacy_single_test(series, "adf", alpha)


def run_kpss_test(
    series: pd.Series,
    alpha: float = 0.05,
) -> tuple[float | None, str]:
    """兼容旧调用的 KPSS 二元结果。"""
    return _legacy_single_test(series, "kpss", alpha)


__all__ = [
    "RESULT_COLUMNS",
    "TABLE_FREQUENCIES",
    "TEST_LABELS",
    "TEST_TREND_LABELS",
    "TEST_TREND_OPTIONS",
    "TRANSFORMATIONS",
    "TransformationSpec",
    "create_correlogram_figure",
    "create_time_series_figure",
    "localize_summary_text",
    "matplotlib_date_compatibility",
    "normalize_frequency",
    "numeric_variable_names",
    "prepare_selected_series",
    "resolve_correlation_lags",
    "resolve_year_over_year_lag",
    "run_adf_test",
    "run_kpss_test",
    "run_selected_stationarity_tests",
    "run_stationarity_tests",
    "summarize_series",
    "transform_series",
]
