"""共享指标卡（st.metric）纯逻辑：最近值、环比、同比百分点与渲染。

供财政金融 / 企业活动 / 劳动就业 三个 part 的指标行复用，与 plot_helpers 同级。
所有数值均由工作簿真实序列派生，不做模拟；系列缺失时对应卡片显示「—」。
"""

from __future__ import annotations

from typing import Any, Iterable


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
    source = item.source if item is not None else ""
    updated = item.updated_at if item is not None else ""
    when = as_of.strftime("%Y-%m") if as_of is not None else "—"
    return f"截至 {when}；{frequency}；来源：{source}；源表更新：{updated}"


__all__ = [
    "_source_note_from_metadata",
    "change_in_points",
    "latest_calendar_yoy_and_pp",
    "latest_month_value",
    "month_over_month_change",
    "pct_delta_text",
    "points_delta_text",
    "render_metric_cards",
]
