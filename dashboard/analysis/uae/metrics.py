"""共享指标卡（st.metric）纯逻辑：最近值、环比、同比百分点与渲染。

供财政金融 / 企业活动 / 劳动就业 三个 part 的指标行复用，与 plot_helpers 同级。
所有数值均由工作簿真实序列派生，不做模拟；系列缺失时对应卡片显示「—」。
"""

from __future__ import annotations

import math
from typing import Any, Iterable

from dashboard.analysis.uae.plot_helpers import translate_source_text


def _clean(series: Any) -> Any:
    return series.dropna().sort_index()


def latest_month_value(series: Any) -> tuple[float | None, object | None]:
    """最近一个有效值及其日期；全部缺失时返回 (None, None)。"""

    clean = _clean(series)
    if clean.empty:
        return None, None
    return float(clean.iloc[-1]), clean.index[-1]


def month_over_month_change(series: Any) -> float | None:
    """环比变化率（%）；上期缺失或上期为 0 时返回 None。"""

    clean = _clean(series)
    if len(clean) < 2:
        return None
    base = float(clean.iloc[-2])
    if base == 0:
        return None
    return (float(clean.iloc[-1]) / base - 1) * 100


def change_in_points(series: Any) -> float | None:
    """较上期的水平差（个百分点/点）；上期缺失时返回 None。"""

    clean = _clean(series)
    if len(clean) < 2:
        return None
    return float(clean.iloc[-1]) - float(clean.iloc[-2])


def latest_calendar_yoy_and_pp(
    values: Any,
    column: str,
) -> tuple[float | None, float | None, object | None]:
    """最新完整月历同比（%）与较上月同比变化（百分点）。

    ``calculate_calendar_yoy`` 缺月时不误用相邻第 12 条观测，保证同比口径正确。
    """

    from dashboard.analysis.uae.government_finance.data import (
        calculate_calendar_yoy,
    )

    yoy = calculate_calendar_yoy(_clean(values[[column]]))
    clean = yoy[column].dropna().sort_index()
    if clean.empty:
        return None, None, None
    latest = float(clean.iloc[-1])
    as_of = clean.index[-1]
    previous = (
        float(clean.iloc[-2]) if len(clean) >= 2 else None
    )
    pp = latest - previous if previous is not None else None
    return latest, pp, as_of


def pct_delta_text(value: float | None) -> str | None:
    """环比：'环比 +12.3%'；None 时返回 None。"""

    if value is None:
        return None
    return f"环比 {value:+.1f}%"


_DISPLAY_SCALES: tuple[tuple[str, float], ...] = (
    ("万亿", 1_000_000_000_000.0),
    ("百亿", 10_000_000_000.0),
    ("十亿", 1_000_000_000.0),
    ("亿", 100_000_000.0),
    ("千万", 10_000_000.0),
    ("百万", 1_000_000.0),
    ("万", 10_000.0),
    ("百", 100.0),
    ("", 1.0),
)


def _format_display_number(value: float) -> str:
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def format_scaled_value(
    value: float | None,
    unit: str,
    *,
    input_scale: float = 1.0,
) -> str | None:
    """按数量级格式化绝对值，保证整数部分不超过三位。

    ``input_scale`` 把输入值换算为 ``unit`` 的基础单位，例如工作簿中的
    ``百万迪拉姆`` 传入 ``unit="迪拉姆", input_scale=1_000_000``。
    百、万、百万、千万、亿、十亿、百亿均可作为显示前缀。
    """

    if value is None:
        return None
    numeric = float(value)
    if not math.isfinite(numeric):
        return None
    base_value = numeric * input_scale
    magnitude = abs(base_value)
    prefix, factor = "", 1.0
    for candidate_prefix, candidate_factor in _DISPLAY_SCALES:
        if magnitude >= candidate_factor:
            prefix, factor = candidate_prefix, candidate_factor
            break
    formatted = _format_display_number(base_value / factor)
    return f"{formatted} {prefix}{unit}"


def format_count_value(value: float | None, unit: str) -> str | None:
    """格式化数量类绝对值，优先使用万、千万、亿等常用单位。"""

    if value is None:
        return None
    numeric = float(value)
    if not math.isfinite(numeric):
        return None
    magnitude = abs(numeric)
    if magnitude < 1_000:
        return f"{numeric:,.0f} {unit}"
    if magnitude < 10_000_000:
        return f"{_format_display_number(numeric / 10_000)} 万{unit}"
    if magnitude < 100_000_000:
        return f"{_format_display_number(numeric / 10_000_000)} 千万{unit}"
    if magnitude < 1_000_000_000:
        return f"{_format_display_number(numeric / 100_000_000)} 亿{unit}"
    if magnitude < 10_000_000_000:
        return f"{_format_display_number(numeric / 1_000_000_000)} 十亿{unit}"
    return f"{_format_display_number(numeric / 10_000_000_000)} 百亿{unit}"


def format_currency_value(
    value: float | None,
    currency: str,
    *,
    input_scale: float = 1.0,
) -> str | None:
    """格式化金额，超过 1,000 亿后使用“万亿”单位。"""

    if value is None:
        return None
    numeric = float(value)
    if not math.isfinite(numeric):
        return None
    base_value = numeric * input_scale
    hundred_million = base_value / 100_000_000
    if abs(hundred_million) < 1_000:
        formatted = _format_display_number(hundred_million)
        return f"{formatted} 亿{currency}"
    formatted = _format_display_number(base_value / 1_000_000_000_000)
    return f"{formatted} 万亿{currency}"


def month_and_year_delta_text(series: Any) -> str | None:
    """返回同一序列的环比与同比文字，缺少任一比较期时单独省略。"""

    clean = _clean(series)
    if clean.empty:
        return None
    month_text = pct_delta_text(month_over_month_change(clean))
    name = clean.name or "指标"
    yoy, _, _ = latest_calendar_yoy_and_pp(
        clean.to_frame(name=name),
        name,
    )
    year_text = None if yoy is None else f"同比 {yoy:+.1f}%"
    parts = [text for text in (month_text, year_text) if text is not None]
    return "；".join(parts) or None


def points_delta_text(
    value: float | None,
    *,
    unit: str = "个百分点",
    digits: int = 2,
) -> str | None:
    """水平差：'较上月 +0.15 个百分点'；None 时返回 None。"""

    if value is None:
        return None
    return f"较上月 {value:+.{digits}f} {unit}"


def render_metric_cards(
    st_obj: Any,
    cards: Iterable[tuple[str, str | None, str | None, str]],
    *,
    n: int = 4,
) -> None:
    """把 4 个 (label, value, delta, help) 渲染成一行 st.metric 卡片。

    主值或 delta 为 None 时展示「—」（同石油活跃钻机数缺失时的降级）。
    """

    columns = st_obj.columns(n)
    for column, (label, value, delta, help_text) in zip(
        columns,
        cards,
        strict=True,
    ):
        with column:
            st_obj.metric(
                label,
                "—" if value is None else value,
                delta=delta,
                delta_color="off",
                help=help_text,
            )


def _source_note_from_metadata(metadata: Any, name: str, as_of: object) -> str:
    """拼 help：截至日期、频率、来源、源表更新。"""

    item = metadata.get(name)
    frequency = item.frequency if item is not None else ""
    source = (
        translate_source_text(item.source)
        if item is not None
        else ""
    )
    updated = item.updated_at if item is not None else ""
    when = as_of.strftime("%Y-%m") if as_of is not None else "—"
    return f"截至 {when}；{frequency}；来源：{source}；源表更新：{updated}"


__all__ = [
    "_source_note_from_metadata",
    "change_in_points",
    "latest_calendar_yoy_and_pp",
    "latest_month_value",
    "month_over_month_change",
    "month_and_year_delta_text",
    "format_scaled_value",
    "format_count_value",
    "format_currency_value",
    "pct_delta_text",
    "points_delta_text",
    "render_metric_cards",
]
